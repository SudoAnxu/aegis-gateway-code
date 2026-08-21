package gateway

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/pprof"
	"os"
	"strings"
	"time"

	"aegis-gateway/internal/identity"
	"aegis-gateway/internal/mutation"
	"aegis-gateway/internal/policy"
	"aegis-gateway/internal/state"
	"aegis-gateway/pkg/telemetry"
)

const gatewayDecisionHeader = "X-Aegis-Gateway-Decision"

// newDownstreamClient creates one long-lived HTTP client/transport for all
// gateway instances. Reusing the transport lets net/http keep connections
// alive and avoids a new TCP connection for every tool invocation. The
// security pipeline remains entirely before forwardRequest: this only changes
// how an already-authorized request is transported downstream.
func newDownstreamClient() *http.Client {
	transport := &http.Transport{
		Proxy: http.ProxyFromEnvironment,
		DialContext: (&net.Dialer{
			Timeout:   5 * time.Second,
			KeepAlive: 30 * time.Second,
		}).DialContext,
		MaxIdleConns:        1024,
		MaxIdleConnsPerHost: 512,
		MaxConnsPerHost:     512,
		IdleConnTimeout:     90 * time.Second,
		TLSHandshakeTimeout: 5 * time.Second,
		ResponseHeaderTimeout: 30 * time.Second,
		ExpectContinueTimeout: 1 * time.Second,
	}
	return &http.Client{Transport: transport, Timeout: 30 * time.Second}
}

type Gateway struct { policyEngine *policy.PolicyEngine; telemetry *telemetry.Telemetry; client *http.Client; toolURLs map[string]string; state *state.Store; auth *identity.Authenticator }
func NewGateway(policyEngine *policy.PolicyEngine, telemetry *telemetry.Telemetry)*Gateway{
	return NewGatewayWithAuth(policyEngine, telemetry, identity.NewTestAuthenticator(identity.StandardTestAgents()))
}
func NewGatewayWithAuth(policyEngine *policy.PolicyEngine, telemetry *telemetry.Telemetry, auth *identity.Authenticator)*Gateway{return &Gateway{policyEngine:policyEngine,telemetry:telemetry,client:newDownstreamClient(),toolURLs:map[string]string{"payments":"http://localhost:8081","files":"http://localhost:8082"},state:state.NewStore(),auth:auth}}

func (g *Gateway) HandleRequest(w http.ResponseWriter,r *http.Request){
	startTime:=time.Now(); pathParts:=strings.Split(strings.TrimPrefix(r.URL.Path,"/"),"/");if len(pathParts)<3||pathParts[0]!="tools"{http.Error(w,"Invalid path. Expected: /tools/:tool/:action",http.StatusBadRequest);return};tool:=pathParts[1];action:=pathParts[2]
	mutation.Set(r.Header.Get("X-Aegis-Mutant-ID"))

	// ── PHASE 1: Identity binding ──────────────────────────────────────
	// Authenticate the identity BEFORE any authorization logic.
	// The model-claimed identity (X-Agent-ID) is NEVER used for authorization.
	id := g.auth.Authenticate(r)
	if !id.Verified {
		// Fail closed: unauthenticated requests are rejected.
		http.Error(w, "Identity verification failed", http.StatusUnauthorized)
		return
	}
	agentID := id.AuthenticatedID
	if mutation.SubstituteFileIdentity()&&tool=="files"{agentID="hr-agent"}
	// ── END PHASE 1 ──────────────────────────────────────────────────

	bodyBytes,err:=io.ReadAll(r.Body);if err!=nil{http.Error(w,fmt.Sprintf("Failed to read request body: %v",err),http.StatusBadRequest);return}
	var params map[string]interface{};malformedOpen:=false
	if len(bodyBytes)>0{if err:=json.Unmarshal(bodyBytes,&params);err!=nil{if !mutation.MalformedFailsOpen(){http.Error(w,fmt.Sprintf("Invalid JSON: %v",err),http.StatusBadRequest);return};params=make(map[string]interface{});malformedOpen=true}}else{params=make(map[string]interface{})}
	paramsHash:=telemetry.HashParams(params)
	allowed,reason:=g.policyEngine.Evaluate(agentID,tool,action,params);if malformedOpen{allowed=true;reason="malformed_bypass"}
	if allowed&&tool=="payments"&&transactionID(params)!=""&&!mutation.WeakenStateReservation(){if stateReason:=g.checkPaymentState(action,params);stateReason!=""{allowed=false;reason=stateReason}}

	// Log identity conflict as audit event (does not affect authorization)
	if id.HasConflict() {
		fmt.Printf("AUDIT: identity spoofing attempt: %s\n", id.ConflictDescription())
	}

	latencyMS:=time.Since(startTime).Milliseconds();ctx,span:=g.telemetry.LogDecision(context.Background(),agentID,tool,action,allowed,reason,paramsHash,latencyMS);defer span.End()
	if !allowed{w.Header().Set(gatewayDecisionHeader,"DENY");w.Header().Set("Content-Type","application/json");w.WriteHeader(http.StatusForbidden);json.NewEncoder(w).Encode(map[string]string{"error":"PolicyViolation","reason":reason});return}
	toolURL,exists:=g.toolURLs[tool];if !exists{if mutation.UnknownToolAllowed(){w.Header().Set(gatewayDecisionHeader,"ALLOW");w.Header().Set("Content-Type","application/json");w.WriteHeader(http.StatusOK);json.NewEncoder(w).Encode(map[string]string{"decision":"ALLOW","tool":tool,"action":action});return};http.Error(w,fmt.Sprintf("Unknown tool: %s",tool),http.StatusBadRequest);return}
	stateReserved:=false
	if tool=="payments"&&transactionID(params)!=""&&!mutation.WeakenStateReservation(){if stateReason:=g.reservePaymentState(action,params);stateReason!=""{w.Header().Set(gatewayDecisionHeader,"DENY");w.Header().Set("Content-Type","application/json");w.WriteHeader(http.StatusForbidden);json.NewEncoder(w).Encode(map[string]string{"error":"PolicyViolation","reason":stateReason});return};stateReserved=action=="create"||action=="refund"}
	w.Header().Set(gatewayDecisionHeader,"ALLOW")
	forwardStart:=time.Now();statusCode,err:=g.forwardRequest(ctx,toolURL,action,bodyBytes,w);forwardLatency:=time.Since(forwardStart).Milliseconds();forwardSpan:=g.telemetry.LogForwardedCall(ctx,tool,action,forwardLatency);defer forwardSpan.End();if err!=nil{if stateReserved{g.abortPaymentState(action,params)};return}
	if mutation.WeakenStateReservation()&&tool=="payments"&&transactionID(params)!=""&&statusCode>=200&&statusCode<300{if action=="create"{_ = g.state.RecordCreate(transactionID(params))};if action=="refund"{_ = g.state.RecordRefund(transactionID(params))}}
	if stateReserved{if statusCode>=200&&statusCode<300{if stateReason:=g.commitPaymentState(action,params);stateReason!=""{return}}else{g.abortPaymentState(action,params)}}
}

// handleEvaluationState seeds benchmark-controlled transaction history without
// forwarding a tool request. It is exposed only when explicitly enabled for
// the isolated evaluation environment. Invalid histories are accepted as
// benchmark state and rejected later by the normal payment state check.
func (g *Gateway) handleEvaluationState(w http.ResponseWriter,r *http.Request){
	if os.Getenv("AEGIS_EVALUATION_MODE") != "1" { http.NotFound(w,r); return }
	if r.Method != http.MethodPost { http.Error(w,"Method not allowed",http.StatusMethodNotAllowed); return }
	var request struct { History []state.HistoryEvent `json:"history"` }
	if err:=json.NewDecoder(r.Body).Decode(&request); err!=nil { http.Error(w,"Invalid evaluation state JSON",http.StatusBadRequest); return }
	_ = g.state.SeedHistory(request.History)
	w.Header().Set("Content-Type","application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{"seeded":true,"history_event_count":len(request.History)})
}

func transactionID(params map[string]interface{})string{if mutation.GlobalTransactionIdentity(){return "__global_transaction__"};for _,key:=range []string{"transaction_id","payment_id"}{if value,ok:=params[key].(string);ok&&strings.TrimSpace(value)!=""{return value}};return ""}
func (g *Gateway) checkPaymentState(action string,params map[string]interface{})string{id:=transactionID(params);switch action{case "create":if err:=g.state.CheckCreate(id);err!=nil{return err.Error()};case "refund":if err:=g.state.CheckRefund(id);err!=nil{return err.Error()}};return ""}
func (g *Gateway) reservePaymentState(action string,params map[string]interface{})string{id:=transactionID(params);switch action{case "create":if err:=g.state.ReserveCreate(id);err!=nil{return err.Error()};case "refund":if err:=g.state.ReserveRefund(id);err!=nil{return err.Error()}};return ""}
func (g *Gateway) commitPaymentState(action string,params map[string]interface{})string{id:=transactionID(params);switch action{case "create":if err:=g.state.CommitCreate(id);err!=nil{return err.Error()};case "refund":if err:=g.state.CommitRefund(id);err!=nil{return err.Error()}};return ""}
func (g *Gateway) abortPaymentState(action string,params map[string]interface{}){id:=transactionID(params);switch action{case "create":g.state.AbortCreate(id);case "refund":g.state.AbortRefund(id)}}
func (g *Gateway) forwardRequest(ctx context.Context,baseURL,action string,body []byte,w http.ResponseWriter)(int,error){url:=fmt.Sprintf("%s/%s",baseURL,action);req,err:=http.NewRequestWithContext(ctx,http.MethodPost,url,bytes.NewReader(body));if err!=nil{return 0,err};req.Header.Set("Content-Type","application/json");resp,err:=g.client.Do(req);if err!=nil{return 0,err};defer resp.Body.Close();for key,values:=range resp.Header{for _,value:=range values{w.Header().Add(key,value)}};w.WriteHeader(resp.StatusCode);_,copyErr:=io.Copy(w,resp.Body);return resp.StatusCode,copyErr}
func (g *Gateway) StartServer(port string)error{mux:=http.NewServeMux();mux.HandleFunc("/tools/",g.HandleRequest);mux.HandleFunc("/__evaluation__/state",g.handleEvaluationState);if os.Getenv("AEGIS_EVALUATION_MODE")=="1"{mux.HandleFunc("/debug/pprof/",pprof.Index);mux.HandleFunc("/debug/pprof/cmdline",pprof.Cmdline);mux.HandleFunc("/debug/pprof/profile",pprof.Profile);mux.HandleFunc("/debug/pprof/symbol",pprof.Symbol);mux.HandleFunc("/debug/pprof/trace",pprof.Trace);mux.Handle("/debug/pprof/goroutine",pprof.Handler("goroutine"));mux.Handle("/debug/pprof/heap",pprof.Handler("heap"));mux.Handle("/debug/pprof/threadcreate",pprof.Handler("threadcreate"));mux.Handle("/debug/pprof/block",pprof.Handler("block"));mux.Handle("/debug/pprof/mutex",pprof.Handler("mutex"))};addr:=":"+port;fmt.Printf("Aegis Gateway listening on %s\n",addr);return http.ListenAndServe(addr,mux)}