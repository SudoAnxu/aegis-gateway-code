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
	Version string        `yaml:"version"`
	Agents  []AgentPolicy `yaml:"agents"`
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

// validatePolicy checks policy structure, supported conditions, and condition types.
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

			for key, value := range allow.Conditions {
				switch key {
				case "min_amount", "max_amount":
					if _, err := numericValue(value, key); err != nil {
						return fmt.Errorf("condition %s: %w", key, err)
					}
				case "currencies":
					if !isStringSlice(value) {
						return fmt.Errorf("condition currencies must be a list of strings")
					}
				case "folder_prefix":
					if _, ok := value.(string); !ok {
						return fmt.Errorf("condition folder_prefix must be a string")
					}
				default:
					return fmt.Errorf("unsupported condition key %q for tool %s", key, allow.Tool)
				}
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
	// Amount constraints.
	minAmount, hasMinAmount := conditions["min_amount"]
	maxAmount, hasMaxAmount := conditions["max_amount"]

	if hasMinAmount || hasMaxAmount {
		amount, exists := params["amount"]
		if !exists {
			return fmt.Errorf("amount is required")
		}

		amountFloat, err := numericValue(amount, "amount")
		if err != nil {
			return err
		}

		if hasMinAmount {
			minFloat, err := numericValue(minAmount, "min_amount")
			if err != nil {
				return err
			}

			if amountFloat < minFloat {
				return fmt.Errorf("Amount below min_amount=%.0f", minFloat)
			}
		}

		if hasMaxAmount {
			maxFloat, err := numericValue(maxAmount, "max_amount")
			if err != nil {
				return err
			}

			if amountFloat > maxFloat {
				return fmt.Errorf("Amount exceeds max_amount=%.0f", maxFloat)
			}
		}
	}

	// Currency constraints.
	if currencies, ok := conditions["currencies"].([]interface{}); ok {
		currency, exists := params["currency"]
		if !exists {
			return fmt.Errorf("currency is required")
		}

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

	// Path constraints.
	if prefix, ok := conditions["folder_prefix"].(string); ok {
		path, exists := params["path"]
		if !exists {
			return fmt.Errorf("path is required")
		}

		pathStr, ok := path.(string)
		if !ok {
			return fmt.Errorf("path must be a string")
		}

		cleanPath := filepath.Clean(pathStr)
		cleanPrefix := filepath.Clean(prefix)

		// The path must either equal the configured directory or be below it.
		// Raw string-prefix matching would incorrectly allow /hr-documents or
		// /hr-docs2 and would not normalize traversal segments safely.
		if cleanPath != cleanPrefix && !filepath.IsAbs(cleanPrefix) {
			return fmt.Errorf("folder_prefix must be an absolute path")
		}

		if cleanPath != cleanPrefix &&
			!hasPathPrefix(cleanPath, cleanPrefix) {
			return fmt.Errorf("Path must remain within prefix %s/", cleanPrefix)
		}
	}

	return nil
}

func hasPathPrefix(path, prefix string) bool {
	prefix = filepath.Clean(prefix)
	if prefix == string(os.PathSeparator) {
		return filepath.IsAbs(path)
	}
	return len(path) > len(prefix) &&
		path[:len(prefix)] == prefix &&
		path[len(prefix)] == os.PathSeparator
}

func isStringSlice(value interface{}) bool {
	switch values := value.(type) {
	case []interface{}:
		for _, value := range values {
			if _, ok := value.(string); !ok {
				return false
			}
		}
		return true
	case []string:
		return true
	default:
		return false
	}
}

func numericValue(value interface{}, name string) (float64, error) {
	switch v := value.(type) {
	case float64:
		return v, nil
	case float32:
		return float64(v), nil
	case int:
		return float64(v), nil
	case int32:
		return float64(v), nil
	case int64:
		return float64(v), nil
	default:
		return 0, fmt.Errorf("%s must be a number", name)
	}
}

// Close stops the policy engine and cleans up resources
func (pe *PolicyEngine) Close() error {
	return pe.watcher.Close()
}
