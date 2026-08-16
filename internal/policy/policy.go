package policy

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"aegis-gateway/internal/mutation"
	"github.com/fsnotify/fsnotify"
	"gopkg.in/yaml.v3"
)

type Policy struct { Version string `yaml:"version"`; Agents []AgentPolicy `yaml:"agents"` }
type AgentPolicy struct { ID string `yaml:"id"`; Allow []ToolAllowance `yaml:"allow"` }
type ToolAllowance struct { Tool string `yaml:"tool"`; Actions []string `yaml:"actions"`; Conditions map[string]interface{} `yaml:"conditions"` }
type PolicyEngine struct { mu sync.RWMutex; policies map[string]*Policy; baseDir string; watcher *fsnotify.Watcher }

func NewPolicyEngine(policiesDir string) (*PolicyEngine, error) {
	pe := &PolicyEngine{policies: make(map[string]*Policy), baseDir: policiesDir}
	watcher, err := fsnotify.NewWatcher(); if err != nil { return nil, fmt.Errorf("failed to create file watcher: %w", err) }
	pe.watcher = watcher
	if err := pe.loadAllPolicies(); err != nil { return nil, err }
	if err := watcher.Add(policiesDir); err != nil { return nil, fmt.Errorf("failed to watch policies directory: %w", err) }
	go pe.watchForChanges(); return pe, nil
}
func (pe *PolicyEngine) loadAllPolicies() error {
	entries, err := os.ReadDir(pe.baseDir); if err != nil { if os.IsNotExist(err) { return fmt.Errorf("policies directory does not exist: %s", pe.baseDir) }; return fmt.Errorf("failed to read policies directory: %w", err) }
	for _, entry := range entries { if entry.IsDir() || (filepath.Ext(entry.Name()) != ".yaml" && filepath.Ext(entry.Name()) != ".yml") { continue }; filePath := filepath.Join(pe.baseDir, entry.Name()); if err := pe.loadPolicyFile(filePath); err != nil { fmt.Printf("ERROR: Failed to load policy file %s: %v\n", filePath, err) } }
	return nil
}
func (pe *PolicyEngine) loadPolicyFile(filePath string) error {
	data, err := os.ReadFile(filePath); if err != nil { return fmt.Errorf("failed to read file: %w", err) }
	var policy Policy; if err := yaml.Unmarshal(data, &policy); err != nil { return fmt.Errorf("failed to parse YAML: %w", err) }
	if err := pe.validatePolicy(&policy); err != nil { return fmt.Errorf("invalid policy: %w", err) }
	pe.mu.Lock(); pe.policies[filePath] = &policy; pe.mu.Unlock(); fmt.Printf("Loaded policy file: %s\n", filePath); return nil
}
func (pe *PolicyEngine) validatePolicy(p *Policy) error {
	if p.Version == "" { return fmt.Errorf("policy version is required") }
	for _, agent := range p.Agents { if agent.ID == "" { return fmt.Errorf("agent ID is required") }; for _, allow := range agent.Allow {
		if allow.Tool == "" { return fmt.Errorf("tool name is required") }; if len(allow.Actions) == 0 { return fmt.Errorf("at least one action is required for tool %s", allow.Tool) }
		for key, value := range allow.Conditions { switch key {
		case "min_amount", "max_amount": if _, err := numericValue(value, key); err != nil { return fmt.Errorf("condition %s: %w", key, err) }
		case "currencies": if !isStringSlice(value) { return fmt.Errorf("condition currencies must be a list of strings") }
		case "folder_prefix": prefix, ok := value.(string); if !ok { return fmt.Errorf("condition folder_prefix must be a string") }; if !filepath.IsAbs(prefix) { return fmt.Errorf("condition folder_prefix must be an absolute path") }
		default: return fmt.Errorf("unsupported condition key %q for tool %s", key, allow.Tool)
		} }
	} }
	return nil
}
func (pe *PolicyEngine) watchForChanges() { for { select {
case event, ok := <-pe.watcher.Events: if !ok { return }; if event.Op&fsnotify.Write == fsnotify.Write || event.Op&fsnotify.Create == fsnotify.Create { time.Sleep(100*time.Millisecond); if err := pe.loadPolicyFile(event.Name); err != nil { fmt.Printf("ERROR: Failed to reload policy file %s: %v\n", event.Name, err) } else { fmt.Printf("Hot-reloaded policy file: %s\n", event.Name) } }; if event.Op&fsnotify.Remove == fsnotify.Remove { pe.mu.Lock(); delete(pe.policies,event.Name); pe.mu.Unlock(); fmt.Printf("Removed policy file: %s\n",event.Name) }
case err, ok := <-pe.watcher.Errors: if !ok { return }; fmt.Printf("ERROR: File watcher error: %v\n",err) } } }
func (pe *PolicyEngine) Evaluate(agentID, tool, action string, params map[string]interface{}) (bool,string) {
	pe.mu.RLock(); defer pe.mu.RUnlock(); knownTool := false
	for _, policy := range pe.policies { for _, agentPolicy := range policy.Agents { for _, allow := range agentPolicy.Allow { if allow.Tool == tool { knownTool=true } }; if !mutation.AgentMatches(agentID,agentPolicy.ID) { continue }; for _, allow := range agentPolicy.Allow { if allow.Tool != tool { continue }; if !mutation.ActionAllowed(hasAction(allow.Actions,action)) { continue }; if allow.Conditions != nil { if err:=pe.checkConditions(allow.Conditions,params); err!=nil { return false,err.Error() } }; return true,"" } } }
	if !knownTool && mutation.UnknownToolAllowed() { return true,"" }
	return false,fmt.Sprintf("Agent %s is not allowed to perform action %s on tool %s",agentID,action,tool)
}
func hasAction(actions []string, action string) bool { for _, a := range actions { if a==action { return true } }; return false }
func (pe *PolicyEngine) checkConditions(conditions map[string]interface{}, params map[string]interface{}) error {
	minAmount, hasMinAmount := conditions["min_amount"]; maxAmount, hasMaxAmount := conditions["max_amount"]; if mutation.SkipMinAmount(){hasMinAmount=false}; if mutation.SkipMaxAmount(){hasMaxAmount=false}
	if hasMinAmount || hasMaxAmount { amount,exists:=params["amount"]; if !exists { if mutation.MissingParameterFailsOpen(){return nil}; return fmt.Errorf("amount is required") }; amountFloat,err:=numericValue(amount,"amount"); if err!=nil { if mutation.UnsupportedTypeFailsOpen(){return nil}; return err }
		if hasMinAmount { minFloat,err:=numericValue(minAmount,"min_amount"); if err!=nil{return err}; if mutation.MinBoundaryOffByOne(){if amountFloat<=minFloat{return fmt.Errorf("Amount below min_amount=%.0f",minFloat)}} else if amountFloat<minFloat{return fmt.Errorf("Amount below min_amount=%.0f",minFloat)} }
		if hasMaxAmount { maxFloat,err:=numericValue(maxAmount,"max_amount"); if err!=nil{return err}; if mutation.MaxBoundaryOffByOne(){if amountFloat>=maxFloat{return fmt.Errorf("Amount exceeds max_amount=%.0f",maxFloat)}} else if amountFloat>maxFloat{return fmt.Errorf("Amount exceeds max_amount=%.0f",maxFloat)} }
	}
	if currencies,ok:=conditions["currencies"].([]interface{}); ok { currency,exists:=params["currency"]; if !exists {if mutation.MissingParameterFailsOpen(){return nil}; return fmt.Errorf("currency is required")}; currencyStr,ok:=currency.(string); if !ok {if mutation.UnsupportedTypeFailsOpen(){return nil}; return fmt.Errorf("currency must be a string")}; allowed:=false; for _,c:=range currencies {if cStr,ok:=c.(string);ok {if mutation.CaseInsensitiveCurrency(){if strings.EqualFold(cStr,currencyStr){allowed=true;break}} else if cStr==currencyStr {allowed=true;break}}}; if !allowed{return fmt.Errorf("Currency %s not in allowed currencies",currencyStr)} }
	if prefix,ok:=conditions["folder_prefix"].(string);ok {if mutation.SkipPathConstraint(){return nil}; path,exists:=params["path"]; if !exists {if mutation.MissingParameterFailsOpen(){return nil};return fmt.Errorf("path is required")}; pathStr,ok:=path.(string);if !ok {if mutation.UnsupportedTypeFailsOpen(){return nil};return fmt.Errorf("path must be a string")};if mutation.RawPathPrefix(){if !strings.HasPrefix(pathStr,prefix){return fmt.Errorf("Path must remain within prefix %s/",prefix)};return nil};cleanPath:=filepath.Clean(pathStr);cleanPrefix:=filepath.Clean(prefix);if !filepath.IsAbs(cleanPrefix){return fmt.Errorf("folder_prefix must be an absolute path")};if cleanPath!=cleanPrefix&&!hasPathPrefix(cleanPath,cleanPrefix){return fmt.Errorf("Path must remain within prefix %s/",cleanPrefix)} }
	return nil
}
func hasPathPrefix(path,prefix string) bool {prefix=filepath.Clean(prefix);if prefix==string(os.PathSeparator){return filepath.IsAbs(path)};return len(path)>len(prefix)&&path[:len(prefix)]==prefix&&path[len(prefix)]==os.PathSeparator}
func isStringSlice(value interface{}) bool {switch values:=value.(type){case []interface{}:for _,value:=range values{if _,ok:=value.(string);!ok{return false}};return true;case []string:return true;default:return false}}
func numericValue(value interface{},name string)(float64,error){switch v:=value.(type){case float64:return v,nil;case float32:return float64(v),nil;case int:return float64(v),nil;case int32:return float64(v),nil;case int64:return float64(v),nil;default:return 0,fmt.Errorf("%s must be a number",name)}}
func (pe *PolicyEngine) Close() error{return pe.watcher.Close()}
