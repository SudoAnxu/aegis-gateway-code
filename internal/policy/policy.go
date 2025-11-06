package policy

import (
	"fmt"
	"os"
	"path/filepath"
	"sync"
	"time"

	"github.com/fsnotify/fsnotify"
	"gopkg.in/yaml.v3"
)

// Policy represents the complete policy configuration
type Policy struct {
	Version string          `yaml:"version"`
	Agents  []AgentPolicy   `yaml:"agents"`
}

// AgentPolicy defines what an agent is allowed to do
type AgentPolicy struct {
	ID    string          `yaml:"id"`
	Allow []ToolAllowance `yaml:"allow"`
}

// ToolAllowance defines allowed tools and actions for an agent
type ToolAllowance struct {
	Tool       string                 `yaml:"tool"`
	Actions    []string               `yaml:"actions"`
	Conditions map[string]interface{} `yaml:"conditions"`
}

// PolicyEngine manages policy evaluation and hot-reload
type PolicyEngine struct {
	mu       sync.RWMutex
	policies map[string]*Policy
	baseDir  string
	watcher  *fsnotify.Watcher
}

// NewPolicyEngine creates a new policy engine with hot-reload support
func NewPolicyEngine(policiesDir string) (*PolicyEngine, error) {
	pe := &PolicyEngine{
		policies: make(map[string]*Policy),
		baseDir:  policiesDir,
	}

	watcher, err := fsnotify.NewWatcher()
	if err != nil {
		return nil, fmt.Errorf("failed to create file watcher: %w", err)
	}
	pe.watcher = watcher

	// Initial load
	if err := pe.loadAllPolicies(); err != nil {
		return nil, err
	}

	// Watch directory for changes
	if err := watcher.Add(policiesDir); err != nil {
		return nil, fmt.Errorf("failed to watch policies directory: %w", err)
	}

	// Start hot-reload goroutine
	go pe.watchForChanges()

	return pe, nil
}

// loadAllPolicies loads all YAML files from the policies directory
func (pe *PolicyEngine) loadAllPolicies() error {
	entries, err := os.ReadDir(pe.baseDir)
	if err != nil {
		if os.IsNotExist(err) {
			return fmt.Errorf("policies directory does not exist: %s", pe.baseDir)
		}
		return fmt.Errorf("failed to read policies directory: %w", err)
	}

	for _, entry := range entries {
		if entry.IsDir() || filepath.Ext(entry.Name()) != ".yaml" && filepath.Ext(entry.Name()) != ".yml" {
			continue
		}

		filePath := filepath.Join(pe.baseDir, entry.Name())
		if err := pe.loadPolicyFile(filePath); err != nil {
			// Log error but continue loading other files
			fmt.Printf("ERROR: Failed to load policy file %s: %v\n", filePath, err)
		}
	}

	return nil
}

// loadPolicyFile loads a single policy file
func (pe *PolicyEngine) loadPolicyFile(filePath string) error {
	data, err := os.ReadFile(filePath)
	if err != nil {
		return fmt.Errorf("failed to read file: %w", err)
	}

	var policy Policy
	if err := yaml.Unmarshal(data, &policy); err != nil {
		return fmt.Errorf("failed to parse YAML: %w", err)
	}

	// Validate policy
	if err := pe.validatePolicy(&policy); err != nil {
		return fmt.Errorf("invalid policy: %w", err)
	}

	pe.mu.Lock()
	pe.policies[filePath] = &policy
	pe.mu.Unlock()

	fmt.Printf("Loaded policy file: %s\n", filePath)
	return nil
}

// validatePolicy checks basic policy structure
func (pe *PolicyEngine) validatePolicy(p *Policy) error {
	if p.Version == "" {
		return fmt.Errorf("policy version is required")
	}

	for _, agent := range p.Agents {
		if agent.ID == "" {
			return fmt.Errorf("agent ID is required")
		}
		for _, allow := range agent.Allow {
			if allow.Tool == "" {
				return fmt.Errorf("tool name is required")
			}
			if len(allow.Actions) == 0 {
				return fmt.Errorf("at least one action is required for tool %s", allow.Tool)
			}
		}
	}

	return nil
}

// watchForChanges handles file system events for hot-reload
func (pe *PolicyEngine) watchForChanges() {
	for {
		select {
		case event, ok := <-pe.watcher.Events:
			if !ok {
				return
			}

			if event.Op&fsnotify.Write == fsnotify.Write || event.Op&fsnotify.Create == fsnotify.Create {
				// Small delay to avoid reading during file write
				time.Sleep(100 * time.Millisecond)
				if err := pe.loadPolicyFile(event.Name); err != nil {
					fmt.Printf("ERROR: Failed to reload policy file %s: %v\n", event.Name, err)
				} else {
					fmt.Printf("Hot-reloaded policy file: %s\n", event.Name)
				}
			}

			if event.Op&fsnotify.Remove == fsnotify.Remove {
				pe.mu.Lock()
				delete(pe.policies, event.Name)
				pe.mu.Unlock()
				fmt.Printf("Removed policy file: %s\n", event.Name)
			}

		case err, ok := <-pe.watcher.Errors:
			if !ok {
				return
			}
			fmt.Printf("ERROR: File watcher error: %v\n", err)
		}
	}
}

// Evaluate checks if an agent is allowed to perform an action on a tool
func (pe *PolicyEngine) Evaluate(agentID, tool, action string, params map[string]interface{}) (allowed bool, reason string) {
	pe.mu.RLock()
	defer pe.mu.RUnlock()

	// Search through all policies
	for _, policy := range pe.policies {
		for _, agentPolicy := range policy.Agents {
			if agentPolicy.ID != agentID {
				continue
			}

			for _, allow := range agentPolicy.Allow {
				if allow.Tool != tool {
					continue
				}

				// Check if action is allowed
				actionAllowed := false
				for _, a := range allow.Actions {
					if a == action {
						actionAllowed = true
						break
					}
				}

				if !actionAllowed {
					continue
				}

				// Check conditions
				if allow.Conditions != nil {
					if err := pe.checkConditions(allow.Conditions, params); err != nil {
						return false, err.Error()
					}
				}

				return true, ""
			}
		}
	}

	return false, fmt.Sprintf("Agent %s is not allowed to perform action %s on tool %s", agentID, action, tool)
}

// checkConditions validates parameters against policy conditions
func (pe *PolicyEngine) checkConditions(conditions map[string]interface{}, params map[string]interface{}) error {
	// Check max_amount condition
	if maxAmount, ok := conditions["max_amount"]; ok {
		if amount, exists := params["amount"]; exists {
			var amountFloat float64
			switch v := amount.(type) {
			case float64:
				amountFloat = v
			case int:
				amountFloat = float64(v)
			case int64:
				amountFloat = float64(v)
			default:
				return fmt.Errorf("amount must be a number")
			}

			var maxFloat float64
			switch v := maxAmount.(type) {
			case float64:
				maxFloat = v
			case int:
				maxFloat = float64(v)
			case int64:
				maxFloat = float64(v)
			default:
				return fmt.Errorf("max_amount must be a number")
			}

			if amountFloat > maxFloat {
				return fmt.Errorf("Amount exceeds max_amount=%.0f", maxFloat)
			}
		}
	}

	// Check currencies condition
	if currencies, ok := conditions["currencies"].([]interface{}); ok {
		if currency, exists := params["currency"]; exists {
			currencyStr, ok := currency.(string)
			if !ok {
				return fmt.Errorf("currency must be a string")
			}

			allowed := false
			for _, c := range currencies {
				if cStr, ok := c.(string); ok && cStr == currencyStr {
					allowed = true
					break
				}
			}

			if !allowed {
				return fmt.Errorf("Currency %s not in allowed currencies", currencyStr)
			}
		}
	}

	// Check folder_prefix condition
	if prefix, ok := conditions["folder_prefix"].(string); ok {
		if path, exists := params["path"]; exists {
			pathStr, ok := path.(string)
			if !ok {
				return fmt.Errorf("path must be a string")
			}

			if len(pathStr) < len(prefix) || pathStr[:len(prefix)] != prefix {
				return fmt.Errorf("Path must start with prefix %s", prefix)
			}
		}
	}

	return nil
}

// Close stops the policy engine and cleans up resources
func (pe *PolicyEngine) Close() error {
	return pe.watcher.Close()
}

