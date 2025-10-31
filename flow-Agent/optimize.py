#!/usr/bin/env python3
import json
import os
import sys
import re
import numpy as np
from typing import Dict, List, Any, Tuple, Optional
import anthropic
import csv
import random
from rag.util import answerWithRAG
from rag.index import load_embeddings_and_docs, build_and_save_embeddings
from sentence_transformers import SentenceTransformer
import torch
from pathlib import Path
from openai import OpenAI
from inspectfuncs import *
from modelfuncs import *
from agglomfuncs import *

print("Python executable:", sys.executable)
print("sys.path:", sys.path[:3])
print("Current working dir:", os.getcwd())

for pkg in ["anthropic", "sentence_transformers", "torch", "openai"]:
    try:
        __import__(pkg)
        print(f"Imported {pkg}")
    except ImportError as e:
        print(f"Failed to import {pkg}: {e}")

def process_log_file(log_path: str) -> Dict[str, Any]:
    """Process a single log file to extract relevant metrics"""
    run_data = {
        'file': os.path.basename(log_path),
        'success': False,
        'metrics': {},
        'errors': []
    }
    
    with open(log_path, 'r') as f:
        content = f.read()
        print(f"File size: {len(content)} characters")
        
        # Extract timing information
        timing_metrics = extract_timing_metrics(content)
        run_data['metrics'].update(timing_metrics)
        
        # Extract wirelength information
        wl_metrics = extract_wirelength_metrics(content)
        run_data['metrics'].update(wl_metrics)
        
        # Extract any errors
        errors = extract_errors(content)
        run_data['errors'].extend(errors)
         # === Inject a simulated error for testing RAG debugging ===
        # if "run3" in log_path:  # You can change it to any run，eg. run1 or run2
        #     fake_error = "[ERROR] TEST_SIM: Simulated routing congestion failure"
        #     print(f"[DEBUG] Injected simulated error in {log_path}: {fake_error}")
        #     run_data['errors'].append(fake_error)
        #     run_data['success'] = False
            
        run_data['success'] = is_run_successful(content, errors)
        
    return run_data

def extract_timing_metrics(log_content: str) -> Dict[str, float]:
    """Extract timing-related metrics from log content"""
    metrics = {}
    
    # Extract worst slack (final)
    slack_match = re.search(r'(?:worst slack|WNS):\s*([-\d.]+)', log_content, re.IGNORECASE)
    if slack_match:
        metrics['worst_slack'] = float(slack_match.group(1))
        
    # Extract CTS worst slack
    # cts_slack_match = re.search(r'(?:CTS|Clock Tree) (?:worst slack|WNS):\s*([-\d.]+)', log_content, re.IGNORECASE)
    cts_slack_match = re.search(r'Timing-driven:\s*(?:worst slack|WNS)\s+([-\d.eE]+)', log_content, re.IGNORECASE)
    if cts_slack_match:
        metrics['cts_ws'] = float(cts_slack_match.group(1))
        
    # Extract clock period
    # period_match = re.search(r'[Cc]lock period:\s*([\d.]+)', log_content)
    period_match = re.search(r'clock period to\s*([\d.]+)', log_content)
    if period_match:
        metrics['clock_period'] = float(period_match.group(1))
        
    # Extract TNS
    # tns_match = re.search(r'(?:Total negative slack|TNS):\s*([-\d.]+)', log_content, re.IGNORECASE)
    tns_match = re.search(r'"finish__timing__setup__tns"\s*:\s*([-\d.eE]+)', log_content)
    if tns_match:
        metrics['tns'] = float(tns_match.group(1))
        
    return metrics

def extract_wirelength_metrics(log_content: str) -> Dict[str, float]:
    """Extract wirelength-related metrics from log content"""
    metrics = {}
    
    # Extract total wirelength
    wl_match = re.search(r'Total wirelength: ([\d.]+)', log_content)
    if wl_match:
        metrics['total_wirelength'] = float(wl_match.group(1))
        
    # Extract estimated wirelength after CTS
    # cts_wl_match = re.search(r'Estimated wirelength: ([\d.]+)', log_content)
    cts_wl_match = re.search(r'"?cts__route__wirelength__estimated"?\s*[:=]\s*([-\d.eE]+)', log_content, re.IGNORECASE)
    if cts_wl_match:
        metrics['cts_wirelength'] = float(cts_wl_match.group(1))
        
    return metrics

def extract_errors(log_content: str) -> List[str]:
    """Extract error messages from log content"""
    errors = []
    
    # Look for common error patterns
    error_patterns = [
        r'Error: .*',
        r'ERROR: .*',
        r'FATAL: .*',
        r'Failed: .*'
    ]
    
    for pattern in error_patterns:
        matches = re.finditer(pattern, log_content, re.MULTILINE)
        errors.extend(match.group(0) for match in matches)
        
    return errors

def is_run_successful(log_content: str, errors: List[str], filename: str = "") -> bool:
    """Determine if a run was successful based on log content and errors"""
    if errors:
        # If any real error lines were found, this file is a failure indicator
        return False
        
    # Look for completion markers
    completion_markers = [
        'Flow complete',
        'Finished successfully'
        'Writing out GDS/OAS',
        '6_report'
    ]
    
    return any(marker in log_content for marker in completion_markers)


class ReActFramework:
    """ReAct framework implementation"""
    
    def __init__(self, client, model_name="DeepSeek-V3"):
        self.client = client
        self.model_name = model_name
        self.conversation_history = []
        
    def add_to_history(self, role: str, content: str):
        """add conversation history"""
        self.conversation_history.append({"role": role, "content": content})
        
    def clear_history(self):
        """clear conversation history"""
        self.conversation_history = []
        
    def extract_thought_action(self, response: str) -> Tuple[str, str, str]:
        """
        Extract Thought, Action, and Action Input from LLM responses
        Format: Thought:... Action:... Action Input: ...
        """
        thought = ""
        action = ""
        action_input = ""
        
        # Extract Thought
        thought_match = re.search(r'Thought:\s*(.*?)(?=\nAction:|$)', response, re.DOTALL)
        if thought_match:
            thought = thought_match.group(1).strip()
            
        # Extract Action
        action_match = re.search(r'Action:\s*(\w+)', response)
        if action_match:
            action = action_match.group(1).strip()
            
        # Extract Action Input
        action_input_match = re.search(r'Action Input:\s*(.*?)(?=\nObservation:|$)', response, re.DOTALL)
        if action_input_match:
            action_input = action_input_match.group(1).strip()
            # Try to parse JSON
            try:
                if action_input.startswith('{') or action_input.startswith('['):
                    action_input = json.loads(action_input)
            except:
                pass  # Maintain the string format

        if "Final Answer:" in response and ("Action:" in response or "Observation:" in response):

            response = response.split("Final Answer:")[0]
            print("Removed premature Final Answer from response")
                
        return thought, action, action_input
        
    def execute_action(self, action: str, action_input: Any, available_tools: Dict) -> str:
        """Execute tool call and return observation results"""
        if action in available_tools:
            try:
                result = available_tools[action](action_input)
                return f"Action executed successfully. Result: {result}"
            except Exception as e:
                return f"Action execution failed: {str(e)}"
        else:
            return f"Unknown action: {action}. Available actions: {list(available_tools.keys())}"
            
    def run_react_cycle(self, 
                       initial_prompt: str, 
                       available_tools: Dict, 
                       max_steps: int = 5,
                       temperature: float = 0.1) -> Dict[str, Any]:
        """
        Run ReAct loop
        
        Args:
            initial_prompt: Initial prompt
            available_tools: Available tool function dictionary
            max_steps: Maximum reasoning steps
            temperature: temperature parameter
            
        Returns:
            a dictionary containing the final result and the reasoning history
        """
        self.clear_history()
        self.add_to_history("user", initial_prompt)
        
        history = []
        final_answer = None
        completed_steps = 0
        
        for step in range(max_steps):
            print(f"\n=== ReAct Step {step + 1}/{max_steps} ===")
            completed_steps = step + 1 

            # Call LLM to obtain response
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=self.conversation_history,
                    temperature=temperature,
                    max_tokens=1024
                )
                
                llm_response = response.choices[0].message.content
                print(f"LLM Response: {llm_response}")
            except Exception as e:
                print(f"Error calling LLM: {e}")
                llm_response = f"Error in LLM call: {e}"
            
            # Extract Thought, Action, Action Input
            thought, action, action_input = self.extract_thought_action(llm_response)
            
            step_data = {
                "step": step + 1,
                "thought": thought,
                "action": action,
                "action_input": action_input,
                "llm_response": llm_response
            }
            
            # Check if it is the final answer
            final_answer_detected = False
            if "Final Answer:" in llm_response:
                final_answer_match = re.search(r'Final Answer:\s*(.*?)$', llm_response, re.DOTALL)
                if final_answer_match:
                    final_answer = final_answer_match.group(1).strip()
                    step_data["final_answer"] = final_answer
                    final_answer_detected = True
                    print(f"Final answer detected at step {step + 1}")

            observation = ""
            # Execute actions and obtain observation results
            if action and not final_answer_detected:
                observation = self.execute_action(action, action_input, available_tools)
                step_data["observation"] = observation
                
                # Update conversation history
                self.add_to_history("assistant", llm_response)
                self.add_to_history("user", f"Observation: {observation}")
                
                print(f"Thought: {thought}")
                print(f"Action: {action}")
                print(f"Action Input: {action_input}")
                print(f"Observation: {observation}")
            else:
                if not final_answer_detected:
                    # If there is no clear action, it may be during the reasoning process
                    self.add_to_history("assistant", llm_response)
                    step_data["observation"] = "No action taken - continuing reasoning"
                    observation = "No action taken"
                else:
                    # If it is the final answer, no further action is required
                    step_data["observation"] = "Final answer provided - cycle complete"
                    observation = "Final answer provided"
                
            history.append(step_data)
            
            if final_answer_detected:
                print(f" ReAct cycle completed at step {step + 1} with final answer")
                break

            # Check if it should end early
            if step >= max_steps - 1:
                final_answer = f"Reached maximum steps ({max_steps}) without final answer"
                print(f" Reached maximum steps without final answer")
                break
        
        if final_answer is None:
            final_answer = "No final answer produced"
        
        return {
            "final_answer": final_answer,
            "reasoning_history": history,
            "success": final_answer is not None and "Reached maximum steps" not in final_answer and "No final answer" not in final_answer,
            "completed_steps": completed_steps,
            "max_steps": max_steps
        }


class OptimizationWorkflow:
    def __init__(self, platform: str, design: str, objective: str):
        self.platform = platform
        self.design = design
        self.objective = objective.upper()  # Convert to uppercase
        
        # Load configuration
        self.config = self._load_config()
        
        # Find the design configuration
        configurations = self.config.get('configurations', [])
        for config in configurations:
            if (
                config['platform'].lower() == self.platform.lower()
                and config['design'].lower() == self.design.lower()
                and config['goal'].upper() == self.objective
            ):
                self.design_config = config
                break
        else:
            raise ValueError(
                f"No configuration found for platform={self.platform}, design={self.design}, objective={self.objective}"
            )
        
        # Define initial clock periods for each design and platform
        initial_clock_periods = {
            ('asap7', 'aes'): 400,     # in picoseconds
            ('asap7', 'ibex'): 1260,   # in picoseconds
            ('asap7', 'jpeg'): 1100,   # in picoseconds
            ('sky130hd', 'aes'): 4.5,  # in nanoseconds
            ('sky130hd', 'ibex'): 10.0,# in nanoseconds
            ('sky130hd', 'jpeg'): 8.0, # in nanoseconds
        }

        # Get the initial clock period for the current platform and design
        key = (self.platform.lower(), self.design.lower())
        if key in initial_clock_periods:
            self.initial_clk_period = initial_clock_periods[key]
        else:
            raise ValueError(f"Initial clock period not defined for platform={self.platform}, design={self.design}")

        # Calculate clock period range
        min_clk = self.initial_clk_period * 0.7
        max_clk = self.initial_clk_period * 1.3

        # Define parameter names in the expected order
        self.parameter_names = [
            'core_util',
            'cell_pad_global',
            'cell_pad_detail', 
            'synth_flatten',
            'pin_layer',
            'above_layer',
            'tns',
            'lb_addon',
            'cts_size',
            'cts_diameter',
            'enable_dpo',
            'clk_period'
        ]
        
        # Set all parameter constraints including clock period range
        self.param_constraints = {
            'core_util': {'type': 'int', 'range': [20, 99]},
            'cell_pad_global': {'type': 'int', 'range': [0, 4]},
            'cell_pad_detail': {'type': 'int', 'range': [0, 4]},
            'synth_flatten': {'type': 'int', 'range': [0, 1]},
            'pin_layer': {'type': 'float', 'range': [0.2, 0.7]},
            'above_layer': {'type': 'float', 'range': [0.2, 0.7]},
            'tns': {'type': 'int', 'range': [70, 100]},
            'lb_addon': {'type': 'float', 'range': [0.00, 0.99]},
            'cts_size': {'type': 'int', 'range': [10, 40]},
            'cts_diameter': {'type': 'int', 'range': [80, 120]},
            'enable_dpo': {'type': 'int', 'range': [0, 1]},
            'clk_period': {'type': 'float', 'range': [min_clk, max_clk]}
        }
        
        # Load initial parameters and SDC context
        self.initial_params = self._load_initial_params()
        self.sdc_context = self._load_sdc_context()

        emb_np, docs, docsDict = load_embeddings_and_docs()
        self.rag_embeddings = torch.tensor(emb_np).cpu()
        self.rag_docs = docs
        self.rag_docsDict = docsDict
        print("[INFO] Loading embedding model...")
        model_path = Path(__file__).parent / "models" / "mxbai-embed-large-v1"
        model_path = model_path.resolve()
        self.rag_model = SentenceTransformer(str(model_path))

        self.react_framework = ReActFramework(
            client=OpenAI(
                base_url="https://ai.gitee.com/v1",
                api_key= #PUT YOUR KEY HERE,
            ),
            model_name="DeepSeek-V3"
        )

    def _create_react_tools(self, stage: str, data: Dict[str, Any]) -> Dict:
        """Create available utility functions for different stages"""
        
        base_tools = {
            "analyze_data_distribution": lambda x: self._call_existing_distribution_analysis(data),
            "analyze_data_structure": lambda x: self._call_existing_structure_analysis(data),
            "evaluate_parameter_ranges": lambda x: self._evaluate_parameter_ranges(data),
            "check_constraints": lambda x: self._check_constraints_compliance(data),
            "suggest_improvements": lambda x: self._suggest_improvements(stage, data),
        }
        
        if stage == 'inspect':
            inspection_tools = {
                "configure_inspection": lambda config: self._configure_inspection_with_existing(config, data),
                "analyze_correlations": lambda params: self._analyze_correlations_with_existing(params, data),
                "cluster_analysis": lambda config: self._cluster_analysis_with_existing(config, data),
                "manifold_analysis": lambda config: self._manifold_analysis_with_existing(config, data),
                "local_structure_analysis": lambda config: self._local_structure_analysis_with_existing(config, data),
            }
            base_tools.update(inspection_tools)

        elif stage == 'model':
            modeling_tools = {
                "configure_model": lambda config: self._configure_model_with_existing(config, data),
                "evaluate_surrogate": lambda params: self._evaluate_surrogate_with_existing(params, data),
                "select_acquisition": lambda method: self._select_acquisition_with_existing(method, data),
                "create_surrogate_model": lambda config: self._create_surrogate_model_with_existing(config, data),
                "evaluate_timing_model": lambda x: self._evaluate_timing_model_with_existing(data),
                "evaluate_wirelength_model": lambda x: self._evaluate_wirelength_model_with_existing(data),
                "get_model_recommendations": lambda x: self._get_model_recommendations_from_existing(data),
            }
            base_tools.update(modeling_tools)
            
        elif stage == 'agglomerate':
            selection_tools = {
                "configure_selection": lambda config: self._configure_selection_with_existing(config, data),
                "generate_parameters": lambda count: self._generate_parameters_with_existing(count, data),
                "validate_parameters": lambda params: self._validate_parameters_tool(params),
                "latin_hypercube_sampling": lambda config: self._latin_hypercube_sampling_with_existing(config, data),
                "create_quality_scores": lambda config: self._create_quality_scores_with_existing(config, data),
                "select_points": lambda config: self._select_points_with_existing(config, data),
                "compare_selection_methods": lambda config: self._compare_selection_methods_with_existing(config, data),
                "kmeans_selection": lambda config: self._kmeans_selection_with_existing(config, data),
                "hybrid_selection": lambda config: self._hybrid_selection_with_existing(config, data),
                "entropy_selection": lambda config: self._entropy_selection_with_existing(config, data),
                "graph_selection": lambda config: self._graph_selection_with_existing(config, data),
            }
            base_tools.update(selection_tools)
            
        return base_tools
    

    def _call_existing_distribution_analysis(self, data: Dict) -> str:
        """Call existing data distribution analysis functions"""
        try:
            X, Y = self._extract_XY_from_data(data)
            
            if X is not None and Y is not None:
                result = inspect_data_distribution(X, Y)
                return self._format_analysis_result("Data Distribution Analysis", result)
            else:
                return "Insufficient data for distribution analysis"
                
        except Exception as e:
            return f"Error in distribution analysis: {str(e)}"

    def _call_existing_structure_analysis(self, data: Dict) -> str:
        """Call existing data structure analysis functions"""
        try:
            X, Y = self._extract_XY_from_data(data)
            
            if X is not None and Y is not None:
                # Use default configuration or retrieve configuration from data
                config = {
                    "n_clusters": 5,
                    "correlation_threshold": 0.5,
                    "n_neighbors": 20,
                    "perplexity": 30
                }
                
                result = inspect_data_structure(X, Y, config)
                return self._format_analysis_result("Data Structure Analysis", result)
            else:
                return "Insufficient data for structure analysis"
                
        except Exception as e:
            return f"Error in structure analysis: {str(e)}"
        
    def _evaluate_parameter_ranges(self, data: Dict) -> str:
        """Evaluation Parameter Range Tool - Implementation"""
        constraints_info = "Parameter Constraints Evaluation:\n"
        
        # Analyze the current usage of parameters
        param_usage = {}
        for run in data.get('log_data', {}).get('runs', []):
            if run.get('parameters'):
                for param, value in run['parameters'].items():
                    if param not in param_usage:
                        param_usage[param] = []
                    param_usage[param].append(float(value))
        
        for param, info in self.param_constraints.items():
            min_val, max_val = info['range']
            param_type = info['type']
            
            constraints_info += f"\n- {param} ({param_type}): range [{min_val}, {max_val}]"
            
            if param in param_usage:
                values = param_usage[param]
                used_min = min(values)
                used_max = max(values)
                constraints_info += f"\n  Currently used: [{used_min:.2f}, {used_max:.2f}]"
                
                # Check if the parameter space has been fully explored
                range_used = (used_max - used_min) / (max_val - min_val)
                if range_used < 0.5:
                    constraints_info += f" (Only {range_used*100:.1f}% of range explored)"
        
        return constraints_info

    def _check_constraints_compliance(self, data: Dict) -> str:
        """Check Constraint Compliance Tool - Implementation"""
        violations = []
        constraint_checks = []
        
        for run in data.get('log_data', {}).get('runs', []):
            if run.get('success') and run.get('parameters'):
                params = run['parameters']
                
                # Check the basic scope constraints
                for param, value in params.items():
                    if param in self.param_constraints:
                        constraint = self.param_constraints[param]
                        min_val, max_val = constraint['range']
                        if value < min_val or value > max_val:
                            violations.append(f"{param}={value} not in [{min_val}, {max_val}]")
                
                # Check domain constraints
                if not self._validate_domain_constraints(params):
                    violations.append(f"Domain constraints violated for run with params: {params}")
        
        if violations:
            constraint_checks.append(f"Constraint violations found in {len(violations)} cases:")
            constraint_checks.extend(violations[:5])  # Only display the first 5
        else:
            constraint_checks.append("All parameters comply with constraints")
        
        # Check the effectiveness of parameter combinations
        successful_count = sum(1 for run in data.get('log_data', {}).get('runs', []) 
                            if run.get('success') and run.get('parameters'))
        total_with_params = sum(1 for run in data.get('log_data', {}).get('runs', []) 
                            if run.get('parameters'))
        
        if total_with_params > 0:
            success_rate = successful_count / total_with_params * 100
            constraint_checks.append(f"\nParameter success rate: {success_rate:.1f}%")
        
        return "\n".join(constraint_checks)

    def _suggest_improvements(self, stage: str, data: Dict) -> str:
        """Provide improvement suggestions based on stages - implementation"""
        suggestions = []
        
        if stage == 'inspect':
            successful_runs = data.get('log_data', {}).get('summary', {}).get('successful_runs', 0)
            total_runs = data.get('log_data', {}).get('summary', {}).get('total_runs', 0)
            
            suggestions.append(f"Inspection Suggestions for {successful_runs}/{total_runs} successful runs:")
            
            if successful_runs < total_runs * 0.3:
                suggestions.append("- Focus on identifying why runs are failing")
                suggestions.append("- Check for common parameter ranges in failed runs")
            else:
                suggestions.append("- Analyze correlations between parameters and objectives")
                suggestions.append("- Identify optimal parameter ranges from successful runs")
        
        elif stage == 'model':
            suggestions.append("Modeling Suggestions:")
            suggestions.append("- Use surrogate models for early prediction of results")
            suggestions.append("- Balance exploration (trying new regions) and exploitation (refining good regions)")
            
            # Suggest modeling methods based on data volume
            successful_runs = data.get('log_data', {}).get('summary', {}).get('successful_runs', 0)
            if successful_runs < 10:
                suggestions.append("- With limited data, use simpler models and focus on exploration")
            else:
                suggestions.append("- With sufficient data, use more complex models and balance exploration/exploitation")
        
        elif stage == 'agglomerate':
            suggestions.append("Parameter Generation Suggestions:")
            suggestions.append("- Generate diverse parameter sets to explore different regions")
            suggestions.append("- Focus on promising parameter ranges identified in previous stages")
            suggestions.append("- Ensure all generated parameters satisfy domain constraints")
            
            # Suggest strategies based on goals
            if self.objective == 'ECP':
                suggestions.append("- For ECP, prioritize timing-critical parameters like clk_period and cell padding")
            elif self.objective == 'DWL':
                suggestions.append("- For DWL, focus on placement and routing parameters")
        
        return "\n".join(suggestions)

    def _extract_XY_from_data(self, data: Dict) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """Extracting X and Y arrays from data - Reusing logic in analyze_stetrics"""
        feature_vectors = []
        objective_values = []
        
        for run in data.get('log_data', {}).get('runs', []):
            if run.get('success') and 'metrics' in run:
                obj_values = self._calculate_objective(run)
                
                if obj_values['value'] is not None or obj_values['surrogate'] is not None:
                    # Extract parameter values as features
                    params = []
                    for param in self.parameter_names:
                        params.append(float(run.get('parameters', {}).get(param, self.initial_params.get(param, 0))))
                    feature_vectors.append(params)
                    
                    # Use real values, if not available, use proxy values
                    objective_values.append(obj_values['value'] if obj_values['value'] is not None else obj_values['surrogate'])
        
        if feature_vectors and objective_values:
            return np.array(feature_vectors), np.array(objective_values)
        else:
            return None, None

    def _format_analysis_result(self, title: str, result: Dict) -> str:
        """Format the analysis result as a readable string"""
        formatted = f"=== {title} ===\n"
        
        for key, value in result.items():
            if key == "model_recommendations":
                formatted += "\n--- Model Recommendations ---\n"
                for rec_key, rec_value in value.items():
                    formatted += f"{rec_key}: {rec_value}\n"
            elif isinstance(value, (int, float)):
                formatted += f"{key}: {value:.4f}\n"
            elif isinstance(value, list) and len(value) > 0 and isinstance(value[0], (int, float)):
                # Format numerical list
                formatted += f"{key}: [{', '.join(f'{v:.4f}' for v in value[:5])}{'...' if len(value) > 5 else ''}]\n"
            else:
                formatted += f"{key}: {value}\n"
        
        return formatted

    def _configure_inspection_with_existing(self, config: Dict, data: Dict) -> str:
        """Use existing function configuration to check parameters"""
        try:
            X, Y = self._extract_XY_from_data(data)
            
            if X is not None and Y is not None:
                # Using configuration to run structural analysis
                result = inspect_data_structure(X, Y, config)
                
                response = f"Inspection configured with: {config}\n"
                response += "Key findings:\n"
                
                # Extract key findings
                if "linearity_score" in result:
                    response += f"- Linearity: {result['linearity_score']:.3f}\n"
                if "is_nonlinear" in result:
                    response += f"- Nonlinear: {result['is_nonlinear']}\n"
                if "needs_local_models" in result:
                    response += f"- Needs local models: {result['needs_local_models']}\n"
                if "cluster_sizes" in result:
                    response += f"- Cluster sizes: {result['cluster_sizes']}\n"
                    
                return response
            else:
                return "No data available for inspection configuration"
                
        except Exception as e:
            return f"Error in inspection configuration: {str(e)}"

    def _analyze_correlations_with_existing(self, params: Dict, data: Dict) -> str:
        """Analyze correlation using existing functions"""
        try:
            X, Y = self._extract_XY_from_data(data)
            
            if X is not None and Y is not None:
                # Perform structural analysis to obtain relevant information
                config = {"correlation_threshold": params.get('threshold', 0.5)}
                result = inspect_data_structure(X, Y, config)
                
                response = "Feature Correlations Analysis:\n"
                
                if "feature_importance" in result:
                    response += "Feature importance (correlation with objective):\n"
                    for i, importance in enumerate(result["feature_importance"]):
                        response += f"- {self.parameter_names[i]}: {importance:.3f}\n"
                        
                if "has_correlated_features" in result:
                    response += f"Has highly correlated features: {result['has_correlated_features']}\n"
                    if "high_correlation_pairs" in result:
                        response += f"High correlation pairs: {result['high_correlation_pairs']}\n"
                        
                return response
            else:
                return "No data available for correlation analysis"
                
        except Exception as e:
            return f"Error in correlation analysis: {str(e)}"

    def _cluster_analysis_with_existing(self, config: Dict, data: Dict) -> str:
        """Cluster analysis using existing functions"""
        try:
            X, Y = self._extract_XY_from_data(data)
            
            if X is not None and Y is not None:
                # Perform structural analysis to obtain clustering information
                result = inspect_data_structure(X, Y, config)
                
                response = "Cluster Analysis:\n"
                
                if "cluster_sizes" in result:
                    response += f"Cluster sizes: {result['cluster_sizes']}\n"
                if "cluster_balance" in result:
                    response += f"Cluster balance: {result['cluster_balance']:.3f}\n"
                if "cluster_y_means" in result:
                    response += "Cluster objective means:\n"
                    for i, mean in enumerate(result["cluster_y_means"]):
                        response += f"- Cluster {i}: {mean:.4f}\n"
                if "needs_local_models" in result:
                    response += f"Recommend local models: {result['needs_local_models']}\n"
                    
                return response
            else:
                return "No data available for cluster analysis"
                
        except Exception as e:
            return f"Error in cluster analysis: {str(e)}"

    def _manifold_analysis_with_existing(self, config: Dict, data: Dict) -> str:
        """Perform manifold analysis using existing functions"""
        try:
            X, Y = self._extract_XY_from_data(data)
            
            if X is not None:
                result = analyze_manifold_structure(X, config)
                return self._format_analysis_result("Manifold Structure Analysis", result)
            else:
                return "No data available for manifold analysis"
                
        except Exception as e:
            return f"Error in manifold analysis: {str(e)}"

    def _local_structure_analysis_with_existing(self, config: Dict, data: Dict) -> str:
        """Using existing functions for local structure analysis"""
        try:
            X, Y = self._extract_XY_from_data(data)
            
            if X is not None:
                result = analyze_local_structure(X, config)
                return self._format_analysis_result("Local Structure Analysis", result)
            else:
                return "No data available for local structure analysis"
                
        except Exception as e:
            return f"Error in local structure analysis: {str(e)}"

    def _get_model_recommendations_from_existing(self, data: Dict) -> str:
        """Obtain model recommendations from existing analysis"""
        try:
            X, Y = self._extract_XY_from_data(data)
            
            if X is not None and Y is not None:
                result = inspect_data_structure(X, Y)
                
                if "model_recommendations" in result:
                    recommendations = result["model_recommendations"]
                    response = "Model Recommendations from Data Analysis:\n"
                    
                    for key, value in recommendations.items():
                        if key == "feature_weights" and isinstance(value, list):
                            response += f"{key}: ["
                            response += ", ".join(f"{w:.3f}" for w in value[:5])
                            if len(value) > 5:
                                response += ", ..."
                            response += "]\n"
                        else:
                            response += f"{key}: {value}\n"
                            
                    return response
                else:
                    return "No model recommendations available"
            else:
                return "No data available for model recommendations"
                
        except Exception as e:
            return f"Error getting model recommendations: {str(e)}"
    
    
    def _configure_model_with_existing(self, config: Dict, data: Dict) -> str:
        """Configure the model using existing functions"""
        try:
            X, Y = self._extract_XY_from_data(data)
            
            if X is not None and Y is not None:
                # Create a model using configuration
                kernel_type = config.get('kernel_type', 'matern')
                preprocessing = config.get('preprocessing', 'standard')
                acquisition = config.get('acquisition', 'ei')
                
                # Create Preprocessor
                preprocessor = create_preprocessor(preprocessing)
                
                # Create acquisition function
                acq_function = create_acquisition_function(acquisition)
                
                response = f"Model configured successfully:\n"
                response += f"- Kernel type: {kernel_type}\n"
                response += f"- Preprocessing: {preprocessing}\n"
                response += f"- Acquisition function: {acquisition}\n"
                response += f"- Data shape: {X.shape}\n"
                
                # If the amount of data is sufficient, a model can be created for testing
                if len(X) >= 2:
                    model = create_model(X, Y, kernel_type=kernel_type)
                    response += f"- Model created successfully with {len(X)} samples\n"
                else:
                    response += f"- Insufficient data for model creation (need at least 2 samples, have {len(X)})\n"
                    
                return response
            else:
                return "No data available for model configuration"
                
        except Exception as e:
            return f"Error in model configuration: {str(e)}"

    def _evaluate_surrogate_with_existing(self, params: Dict, data: Dict) -> str:
        """Evaluate the proxy model using existing functions"""
        try:
            X, Y = self._extract_XY_from_data(data)
            
            if X is not None and Y is not None:
                # Extract proxy values (if any)
                surrogate_values = None
                if 'surrogates' in data.get('metrics', {}):
                    surrogate_values = np.array(data['metrics']['surrogates'])
                
                # Use existing functions to process proxy data
                if surrogate_values is not None:
                    X_processed, y_combined, uncertainty = handle_surrogate_data(X, Y, surrogate_values)
                    
                    response = "Surrogate Model Evaluation:\n"
                    response += f"- Original data points: {len(Y)}\n"
                    response += f"- Valid target values: {np.sum(~np.isnan(Y))}\n"
                    response += f"- Surrogate values used: {np.sum(np.isnan(Y))}\n"
                    response += f"- Combined data points: {len(y_combined)}\n"
                    
                    if len(uncertainty) > 0:
                        response += f"- Average surrogate uncertainty: {np.mean(uncertainty):.4f}\n"
                        
                    return response
                else:
                    return "No surrogate data available for evaluation"
            else:
                return "No data available for surrogate evaluation"
                
        except Exception as e:
            return f"Error in surrogate evaluation: {str(e)}"

    def _select_acquisition_with_existing(self, method: str, data: Dict) -> str:
        """Use existing functions to select collection functions"""
        try:
            # Create a collection function using an existing function
            acq_function = create_acquisition_function(method)
            
            response = f"Acquisition function selected: {method.upper()}\n"
            
            # Provide explanations for different collection functions
            explanations = {
                'ei': "Expected Improvement - balances improvement probability and magnitude",
                'ucb': "Upper Confidence Bound - favors exploration of uncertain regions",
                'pi': "Probability of Improvement - focuses on areas likely to improve",
                'augmented_ei': "Augmented EI - combines EI with exploration bonus"
            }
            
            response += f"Explanation: {explanations.get(method, 'No explanation available')}\n"
            
            # Provide recommendations based on data characteristics
            X, Y = self._extract_XY_from_data(data)
            if X is not None and Y is not None:
                if len(Y) < 10:
                    response += "Recommendation: With limited data, consider using UCB for better exploration\n"
                else:
                    response += "Recommendation: With sufficient data, EI or Augmented EI are good choices\n"
                    
            return response
            
        except Exception as e:
            return f"Error in acquisition function selection: {str(e)}"

    def _create_surrogate_model_with_existing(self, config: Dict, data: Dict) -> str:
        """Create a proxy model using existing functions"""
        try:
            X, Y = self._extract_XY_from_data(data)
            
            if X is not None and Y is not None:
                kernel_type = config.get('kernel_type', 'matern')
                noise_level = config.get('noise_level', 1e-6)
                
                # Create a model using existing functions
                model = create_model(X, Y, noise_level=noise_level, kernel_type=kernel_type)
                
                response = f"Surrogate Model Created:\n"
                response += f"- Kernel: {kernel_type}\n"
                response += f"- Data points: {len(X)}\n"
                response += f"- Features: {X.shape[1]}\n"
                response += f"- Kernel parameters: {model.kernel_}\n"
                
                # Test model prediction
                if len(X) > 0:
                    predictions, stds = predict_with_model(model, X[:1])  # Test a point
                    response += f"- Test prediction successful\n"
                    response += f"- Prediction range: [{predictions[0]:.4f} ± {stds[0]:.4f}]\n"
                    
                return response
            else:
                return "No data available for model creation"
                
        except Exception as e:
            return f"Error in surrogate model creation: {str(e)}"

    def _evaluate_timing_model_with_existing(self, data: Dict) -> str:
        """Evaluate timing models using existing functions"""
        try:
            # Build context
            context = {
                'log_data': data.get('log_data', {}),
                'metrics': data.get('metrics', {}),
                'model_recommendations': data.get('model_recommendations', {})
            }
            
            # Evaluate timing models using existing functions
            results = evaluate_timing_model(context)
            
            response = "Timing Model Evaluation:\n"
            
            if 'performance' in results:
                for key, value in results['performance'].items():
                    response += f"- {key}: {value:.4f}\n"
                    
            if 'suggestions' in results:
                response += "\nSuggestions:\n"
                for suggestion in results['suggestions']:
                    response += f"- {suggestion}\n"
                    
            if 'recommendations' in results:
                response += "\nRecommendations:\n"
                for key, value in results['recommendations'].items():
                    response += f"- {key}: {value}\n"
                    
            return response
            
        except Exception as e:
            return f"Error in timing model evaluation: {str(e)}"

    def _evaluate_wirelength_model_with_existing(self, data: Dict) -> str:
        """Evaluate the wire length model using existing functions"""
        try:
            # Build context
            context = {
                'log_data': data.get('log_data', {}),
                'metrics': data.get('metrics', {}),
                'model_recommendations': data.get('model_recommendations', {})
            }
            
            # Evaluate the wire length model using existing functions
            results = evaluate_wirelength_model(context)
            
            response = "Wirelength Model Evaluation:\n"
            
            if 'performance' in results:
                for key, value in results['performance'].items():
                    response += f"- {key}: {value:.4f}\n"
                    
            if 'suggestions' in results:
                response += "\nSuggestions:\n"
                for suggestion in results['suggestions']:
                    response += f"- {suggestion}\n"
                    
            if 'recommendations' in results:
                response += "\nRecommendations:\n"
                for key, value in results['recommendations'].items():
                    response += f"- {key}: {value}\n"
                    
            return response
            
        except Exception as e:
            return f"Error in wirelength model evaluation: {str(e)}"

    def _generate_parameters_with_existing(self, count: int, data: Dict) -> str:
        """Generate parameters using existing functions"""
        try:
            if count <= 0 or count > 50:
                return "Error: count must be between 1 and 50"
            
            # Obtain parameter dimensions
            n_dims = len(self.parameter_names)
            
            # Use existing Latin hypercube sampling
            samples = latin_hypercube(count, n_dims)
            
            response = f"Parameter Generation using Latin Hypercube:\n"
            response += f"- Samples generated: {count}\n"
            response += f"- Parameter dimensions: {n_dims}\n"
            response += f"- Sampling method: Latin Hypercube\n"
            
            # Display parameter range information
            response += "\nParameter Ranges:\n"
            for i, param in enumerate(self.parameter_names):
                constraint = self.param_constraints[param]
                min_val, max_val = constraint['range']
                response += f"- {param}: [{min_val}, {max_val}] ({constraint['type']})\n"
                
            return response
            
        except Exception as e:
            return f"Error in parameter generation: {str(e)}"

    def _latin_hypercube_sampling_with_existing(self, config: Dict, data: Dict) -> str:
        """Using existing functions for Latin hypercube sampling"""
        try:
            n_points = config.get('n_points', 10)
            n_dims = len(self.parameter_names)
            
            # Use the existing Latin hypercube sampling function
            samples = latin_hypercube(n_points, n_dims)
            
            response = f"Latin Hypercube Sampling:\n"
            response += f"- Points: {n_points}\n"
            response += f"- Dimensions: {n_dims}\n"
            response += f"- Sample shape: {samples.shape}\n"
            
            # Display sampling statistics
            response += f"- Sample range: [{samples.min():.3f}, {samples.max():.3f}]\n"
            response += f"- Sample mean: {samples.mean():.3f}\n"
            response += f"- Sample std: {samples.std():.3f}\n"
            
            return response
            
        except Exception as e:
            return f"Error in Latin hypercube sampling: {str(e)}"
    
    def _configure_selection_with_existing(self, config: Dict, data: Dict) -> str:
        """Configure selection strategy using existing functions"""
        try:
            method = config.get('method', 'hybrid')
            quality_weight = config.get('quality_weight', 0.7)
            uncertainty_bonus = config.get('uncertainty_bonus', 0.2)
            n_points = config.get('n_points', 10)
            
            response = f"Selection Strategy Configured:\n"
            response += f"- Method: {method}\n"
            response += f"- Quality weight: {quality_weight}\n"
            response += f"- Uncertainty bonus: {uncertainty_bonus}\n"
            response += f"- Points to select: {n_points}\n"
            
            # Provide explanations for different methods
            method_descriptions = {
                "kmeans": "K-means clustering - selects best point from each cluster",
                "hybrid": "Hybrid approach - balances quality and diversity",
                "entropy": "Entropy-based - maximizes information diversity", 
                "graph": "Graph-based - uses network centrality measures"
            }
            
            response += f"Method description: {method_descriptions.get(method, 'No description')}\n"
            
            return response
            
        except Exception as e:
            return f"Error in selection configuration: {str(e)}"

    
    def _create_quality_scores_with_existing(self, config: Dict, data: Dict) -> str:
        """Create a quality score using an existing function"""
        try:
            # Extract necessary information from data
            X, Y = self._extract_XY_from_data(data)
            
            if X is not None and Y is not None:
                # Simulation model predictions and uncertainties (in practical use, these should come from real models)
                model_predictions = Y  # Using real values as a proxy for prediction
                model_uncertainties = np.ones_like(Y) * 0.1  # Simulate uncertainty
                
                # Create a quality score using an existing function
                quality_scores = create_quality_scores(X, Y, model_predictions, model_uncertainties)
                
                response = "Quality Scores Created:\n"
                response += f"- Data points: {len(X)}\n"
                response += f"- Quality score range: [{quality_scores.min():.4f}, {quality_scores.max():.4f}]\n"
                response += f"- Quality score mean: {quality_scores.mean():.4f}\n"
                response += f"- Quality score std: {quality_scores.std():.4f}\n"
                
                response += f"- First 5 quality scores: {quality_scores[:5].tolist()}\n"
                
                if 'selection_data' not in data:
                    data['selection_data'] = {}
                data['selection_data']['quality_scores'] = quality_scores
                data['selection_data']['X'] = X
                data['selection_data']['Y'] = Y
                
                return response
            else:
                return "No data available for quality score creation"
                
        except Exception as e:
            return f"Error in quality score creation: {str(e)}"

    def _select_points_with_existing(self, config: Dict, data: Dict) -> str:
        """_select_points_with_existing"""
        try:
            selection_data = data.get('selection_data', {})
            quality_scores = selection_data.get('quality_scores')
            X = selection_data.get('X')
            
            if X is not None and quality_scores is not None:
                method = config.get('method', 'hybrid')
                n_points = config.get('n_points', 10)
                quality_weight = config.get('quality_weight', 0.7)
                
                selection_config = {
                    "quality_weight": quality_weight,
                    "uncertainty_bonus": config.get('uncertainty_bonus', 0.2)
                }
                
                selected_indices = select_points(
                    X, quality_scores, 
                    method=method, 
                    n_points=n_points,
                    config=selection_config
                )
                
                response = f"Points Selected using {method.upper()} method:\n"
                response += f"- Selected {len(selected_indices)} points\n"
                response += f"- Selected indices: {selected_indices.tolist()}\n"
                
                selected_qualities = quality_scores[selected_indices]
                response += f"- Selected quality scores: {selected_qualities.tolist()}\n"
                response += f"- Average quality of selected: {selected_qualities.mean():.4f}\n"
                
                # store selection data
                data['selection_data']['selected_indices'] = selected_indices
                
                return response
            else:
                return "No quality scores available. Please run 'create_quality_scores' first."
                
        except Exception as e:
            return f"Error in point selection: {str(e)}"

    def _compare_selection_methods_with_existing(self, config: Dict, data: Dict) -> str:
        """compare selection methods with existing("""
        try:
            selection_data = data.get('selection_data', {})
            quality_scores = selection_data.get('quality_scores')
            X = selection_data.get('X')
            
            if X is not None and quality_scores is not None:
                n_points = config.get('n_points', 5)
                methods = ['kmeans', 'hybrid', 'entropy', 'graph']
                
                response = "Selection Method Comparison:\n"
                response += f"- Comparing {len(methods)} methods\n"
                response += f"- Points to select: {n_points}\n\n"
                
                for method in methods:
                    try:
                        selected_indices = select_points(
                            X, quality_scores, 
                            method=method, 
                            n_points=n_points
                        )
                        
                        selected_qualities = quality_scores[selected_indices]
                        
                        response += f"**{method.upper()}**:\n"
                        response += f"  - Selected indices: {selected_indices.tolist()}\n"
                        response += f"  - Avg quality: {selected_qualities.mean():.4f}\n"
                        response += f"  - Quality range: [{selected_qualities.min():.4f}, {selected_qualities.max():.4f}]\n"
                        
                    except Exception as e:
                        response += f"**{method.upper()}**: Error - {str(e)}\n"
                        
                return response
            else:
                return "No quality scores available. Please run 'create_quality_scores' first."
                
        except Exception as e:
            return f"Error in method comparison: {str(e)}"

    def _kmeans_selection_with_existing(self, config: Dict, data: Dict) -> str:
        """using K-means selection method"""
        try:
            selection_data = data.get('selection_data', {})
            quality_scores = selection_data.get('quality_scores')
            X = selection_data.get('X')
            
            if X is not None and quality_scores is not None:
                n_points = config.get('n_points', 10)
                
                # using K-means selecting function
                selected_indices = kmeans_select(X, quality_scores, n_points)
                
                response = "K-means Selection Results:\n"
                response += f"- Selected {len(selected_indices)} points\n"
                response += f"- Selected indices: {selected_indices.tolist()}\n"
                
                selected_qualities = quality_scores[selected_indices]
                response += f"- Average quality: {selected_qualities.mean():.4f}\n"
                response += f"- Quality diversity: {selected_qualities.std():.4f}\n"
                
                # store results
                data['selection_data']['selected_indices'] = selected_indices
                data['selection_data']['method_used'] = 'kmeans'
                
                return response
            else:
                return "No quality scores available. Please run 'create_quality_scores' first."
                
        except Exception as e:
            return f"Error in K-means selection: {str(e)}"

    def _hybrid_selection_with_existing(self, config: Dict, data: Dict) -> str:
        """using existing hybrid selection method"""
        try:
            selection_data = data.get('selection_data', {})
            quality_scores = selection_data.get('quality_scores')
            X = selection_data.get('X')
            
            if X is not None and quality_scores is not None:
                n_points = config.get('n_points', 10)
                quality_weight = config.get('quality_weight', 0.7)
                
                distance_matrix = cdist(X, X)
                
                # using hybrid_select function
                selected_indices = hybrid_select(
                    X, quality_scores, distance_matrix, 
                    n_points, quality_weight
                )
                
                response = "Hybrid Selection Results:\n"
                response += f"- Selected {len(selected_indices)} points\n"
                response += f"- Quality weight: {quality_weight}\n"
                response += f"- Selected indices: {selected_indices.tolist()}\n"
                
                selected_qualities = quality_scores[selected_indices]
                response += f"- Average quality: {selected_qualities.mean():.4f}\n"
                
                selected_points = X[selected_indices]
                min_distances = np.min(cdist(selected_points, selected_points) + np.eye(len(selected_points)) * 1e6, axis=1)
                response += f"- Minimum inter-point distance: {min_distances.mean():.4f}\n"
                
                # store results
                data['selection_data']['selected_indices'] = selected_indices
                data['selection_data']['method_used'] = 'hybrid'
                
                return response
            else:
                return "No quality scores available. Please run 'create_quality_scores' first."
                
        except Exception as e:
            return f"Error in hybrid selection: {str(e)}"

    def _entropy_selection_with_existing(self, config: Dict, data: Dict) -> str:
        """using existing entropy selecting methods"""
        try:
            selection_data = data.get('selection_data', {})
            quality_scores = selection_data.get('quality_scores')
            X = selection_data.get('X')
            
            if X is not None and quality_scores is not None:
                n_points = config.get('n_points', 10)
                
                # using entropy selecting function
                selected_indices = entropy_select(X, quality_scores, n_points)
                
                response = "Entropy-based Selection Results:\n"
                response += f"- Selected {len(selected_indices)} points\n"
                response += f"- Selected indices: {selected_indices.tolist()}\n"
                
                selected_qualities = quality_scores[selected_indices]
                response += f"- Average quality: {selected_qualities.mean():.4f}\n"
                
                # store results
                data['selection_data']['selected_indices'] = selected_indices
                data['selection_data']['method_used'] = 'entropy'
                
                return response
            else:
                return "No quality scores available. Please run 'create_quality_scores' first."
                
        except Exception as e:
            return f"Error in entropy selection: {str(e)}"

    def _graph_selection_with_existing(self, config: Dict, data: Dict) -> str:
        """using existing graph selection method"""
        try:
            selection_data = data.get('selection_data', {})
            quality_scores = selection_data.get('quality_scores')
            X = selection_data.get('X')
            
            if X is not None and quality_scores is not None:
                n_points = config.get('n_points', 10)
                
                # using graph selecting function
                selected_indices = graph_select(X, quality_scores, n_points)
                
                response = "Graph-based Selection Results:\n"
                response += f"- Selected {len(selected_indices)} points\n"
                response += f"- Selected indices: {selected_indices.tolist()}\n"
                
                selected_qualities = quality_scores[selected_indices]
                response += f"- Average quality: {selected_qualities.mean():.4f}\n"
                
                # store results
                data['selection_data']['selected_indices'] = selected_indices
                data['selection_data']['method_used'] = 'graph'
                
                return response
            else:
                return "No quality scores available. Please run 'create_quality_scores' first."
                
        except Exception as e:
            return f"Error in graph selection: {str(e)}"


    def _validate_parameters_tool(self, params: Dict) -> str:
        validation_results = []
        
        for param_name, value in params.items():
            if param_name in self.param_constraints:
                constraint = self.param_constraints[param_name]
                min_val, max_val = constraint['range']
                param_type = constraint['type']
                
                if value < min_val or value > max_val:
                    validation_results.append(f" {param_name}={value} outside range [{min_val}, {max_val}]")
                else:
                    validation_results.append(f" {param_name}={value} within valid range")
        
        if self._validate_domain_constraints(params):
            validation_results.append("Domain constraints satisfied")
        else:
            validation_results.append("Domain constraints violated")
        
        return "Parameter Validation:\n" + "\n".join(validation_results)
        
        
    def _load_config(self) -> Dict[str, Any]:
        """Load the configuration from 'opt_config.json'."""
        with open('opt_config.json', 'r') as f:
            config = json.load(f)
        return config
        
    def _load_initial_params(self) -> Dict[str, Any]:
        """Load initial parameters from the design's config.mk file"""
        config_path = f"designs/{self.platform}/{self.design}/config.mk"
        params = {}
        with open(config_path, 'r') as f:
            for line in f:
                if line.startswith('export'):
                    parts = line.strip().split('=', 1)
                    if len(parts) == 2:
                        key = parts[0].replace('export', '').strip()
                        value = parts[1].strip()
                        params[key] = value
        return params
        
    def _load_sdc_context(self) -> Dict[str, Any]:
        """Load SDC context including special case for JPEG"""
        sdc_context = {}
        
        # Determine SDC filename based on platform/design
        if self.platform.lower() == 'asap7' and self.design.lower() == 'jpeg':
            sdc_file = 'jpeg_encoder15_7nm.sdc'
        else:
            sdc_file = 'constraint.sdc'
            
        sdc_path = f"designs/{self.platform}/{self.design}/{sdc_file}"
        
        # Read SDC file
        try:
            with open(sdc_path, 'r') as f:
                sdc_content = f.read()
                
            # Extract clock period
            clock_period_match = re.search(r'set clk_period\s+([\d.]+)', sdc_content)
            if clock_period_match:
                sdc_context['clock_period'] = float(clock_period_match.group(1))
                
            # Store full content for context
            sdc_context['content'] = sdc_content
            sdc_context['filename'] = sdc_file
            
        except Exception as e:
            print(f"Warning: Could not load SDC file {sdc_path}: {str(e)}")
            sdc_context['error'] = str(e)
            
        return sdc_context
        

    def _generate_llm_prompt(self, stage: str, data: Dict[str, Any]) -> str:

        constraints_text = "Parameter Constraints:\n"
        for param, info in self.param_constraints.items():
            param_type = info['type']
            param_range = info['range']
            constraints_text += f"- {param} ({param_type}, range: {param_range})\n"

        tool_instructions = {
            'inspect': (
                f"**Stage: Inspect**\n"
                "In this stage, we analyze the data from previous optimization runs to identify patterns, trends, and insights.\n\n"
                f"Data to analyze:\n{json.dumps(data, indent=2, default=str)}\n\n"
                "Please analyze the data and provide insights on:\n"
                "1. Key patterns in successful vs unsuccessful runs.\n"
                "2. Parameter ranges that appear promising.\n"
                "3. Any timing or wirelength trends.\n"
                "4. Recommendations for subsequent runs.\n"
                "5. We hope to further reduce the total wirelength.\n"
            ),
            
            'model': (
                f"**Stage: Model**\n"
                "In this stage, we decide how to model the optimization problem based on the data analysis.\n\n"
                f"Data for modeling:\n{json.dumps(data, indent=2, default=str)}\n\n"
                "Please suggest:\n"
                "1. Appropriate modeling techniques.\n"
                "2. Key parameters to focus on.\n"
                "3. Surrogate model recommendations.\n"
                "4. Acquisition function choices.\n"
            ),
            
            'agglomerate': (
                f"**Stage: Agglomerate**\n"
                "In this stage, we generate new parameter combinations to explore in the next optimization runs.\n\n"
                "Please provide a list of new parameter sets to try, ensuring they respect the domain constraints below.\n\n"
                f"{constraints_text}\n"
                "Each parameter set should be a dictionary with parameter names and their suggested values.\n"
                "**Important:** Make sure all parameter sets satisfy the domain constraints before suggesting them.\n"
            )
        }
        
        stage_contexts = {
            'inspect': (
                f"metrics analyze: Total runs={data.get('log_data', {}).get('summary', {}).get('total_runs', 0)}, "
                f"successful runs ={data.get('log_data', {}).get('summary', {}).get('successful_runs', 0)}"
            ),
            'model': "Configure modeling methods based on inspection results",
            'agglomerate': "Configure parameter selection strategy based on modeling results"
        }
        
        prompt = f"""**stages:{stage.upper()}**

        {stage_contexts.get(stage, '')}

        {tool_instructions.get(stage, '')}

        **Important: Use only tool calls and do not generate text replies!**
        """

        # ========= Splicing RAG =========
        rag_context = ""
        if self.rag_model is not None and self.rag_embeddings is not None:
            try:
                print("[DEBUG] RAG: Starting retrieval...")

                # Step 1: Extract error information
                error_summary = ""
                if "log_data" in data:
                    all_errors = []
                    for run in data["log_data"].get("runs", []):
                        if run.get("errors"):
                            all_errors.extend(run["errors"])
                    if all_errors:
                        # Retrieve the most recent or frequent errors
                        top_errors = all_errors[-3:]  # Last 3 posts
                        error_summary = "\n".join(top_errors)
                        print(f"[DEBUG] Detected {len(all_errors)} error messages. Sample:\n{error_summary}")

                # Step 2: Construct RAG query
                if error_summary:
                    query = (
                        f"Stage: {stage}. Objective: {self.objective}. "
                        f"The recent optimization runs failed with errors:\n{error_summary}\n\n"
                        "Retrieve relevant OpenROAD documentation, known failure modes, and "
                        "potential parameter tuning suggestions that may fix these issues."
                    )
                else:
                    query = (
                        f"Stage: {stage}. Objective: {self.objective}. "
                        f"Focus on analyzing {stage}-related optimization results. "
                        f"Important metrics include wirelength, timing, area, and success rate. "
                        f"Find relevant OpenROAD documentation, parameter tuning guides, and failure pattern examples."
                    )

                # Step 3: Execute search
                rag_context = answerWithRAG(
                    query,
                    self.rag_embeddings,
                    self.rag_model,
                    self.rag_docs,
                    self.rag_docsDict,
                )

                if isinstance(rag_context, dict):  # If returning dict
                    print(f"[DEBUG] RAG Retrieved {len(rag_context.get('docs', []))} related entries.")
                    for doc in rag_context.get("docs", [])[:3]:
                        print(f"  ↳ {doc['title']} (score={doc['score']:.3f}) from {doc['source']}")
                    retrieved_text = rag_context.get("content", "")
                else:
                    retrieved_text = rag_context

                # Step 4: add to prompt
                if retrieved_text.strip():
                    prompt += (
                        "\n\n=== Retrieved OpenROAD Documentation (via RAG) ===\n"
                        f"{retrieved_text}\n"
                        "=============================================="
                    )
                    print("[DEBUG] RAG: Context successfully added to prompt.")
                else:
                    print("[DEBUG] RAG: Empty context retrieved.")
            except Exception as e:
                prompt += f"\n\n[WARN] RAG retrieval failed: {e}"

        if "log_data" in data:
            all_errors = []
            for run in data["log_data"].get("runs", []):
                if run.get("errors"):
                    all_errors.extend(run["errors"])

            if all_errors:
                error_summary = "\n".join(all_errors[-5:])  # The last 5 errors
                prompt += f"""

        ### Detected Run Errors
        {error_summary}

        The model must now act as an **EDA Debugging Assistant**.
        Using the retrieved documentation and knowledge, analyze the errors above and:
        1. Identify the root causes of each error (e.g., tool misconfiguration, parameter overflow, timing issues, etc.)
        2. Suggest **specific parameter changes or flow adjustments** to prevent these errors.
        3. Indicate whether the error is likely due to constraints, routing congestion, or timing margin.
        4. Provide a short explanation for each suggestion.

        Output format:
        Error Diagnosis:
        - Root Cause: ...
        - Recommended Fix: ...
        - Suggested Parameter Change: ...
        - Reason: ...

        """
                print("[DEBUG] Added error-fix section to prompt.")
    def _collect_recent_errors(self, data: Dict[str, Any], max_errors=5) -> str:
        errors = []
        for run in data.get("log_data", {}).get("runs", []):
            if run.get("errors"):
                errors.extend(run["errors"])
        print(f"[DEBUG] Found total {len(errors)} errors in all runs.")
        return "\n".join(errors[-max_errors:]) if errors else "No errors detected."

    def _call_llm(self, stage: str, data: Dict[str, Any]) -> Dict[str, Any]:
        # """Call Claude to get recommendations for optimization parameters"""
        # print(f"\n=== Calling LLM for {stage} stage ===")
        """Call LLM to get recommendations for optimization parameters using react framework"""
        print(f"\n=== Calling LLM with ReAct framework for {stage} stage ===")

        try:
            react_prompt = self._generate_react_prompt(stage, data)
            print(f"Generated prompt with context for {stage}")
            print("=== Context Message ===")
            print(react_prompt)
            print("========================")
            available_tools = self._create_react_tools(stage, data)

            react_result = self.react_framework.run_react_cycle(
                initial_prompt=react_prompt,
                available_tools=available_tools,
                max_steps=3,  
                temperature=0.1
            )
            # === If an error occurs, enter Debug mode ===
            if "log_data" in data and any(run.get("errors") for run in data["log_data"].get("runs", [])):
                print("\n[DEBUG] Detected errors in previous runs. Invoking Debug Assistant mode...")

                # Collect error information
                all_errors = []
                for run in data["log_data"]["runs"]:
                    if run.get("errors"):
                        all_errors.extend(run["errors"])
                error_text = "\n".join(all_errors[-5:])  # Recent entries

                # Construct a Debug Prompt
                debug_prompt = f"""
            You are now an **EDA Debugging Expert**.
            Based on the following OpenROAD errors and RAG documentation, analyze and provide concrete repair suggestions.

            Errors Detected:
            {error_text}

            Please identify:
            1. Root cause of each error.
            2. Specific parameter changes (e.g., in floorplan, CTS, or routing stages) that could fix the issue.
            3. Whether this issue is due to timing, congestion, or setup misconfiguration.
            4. One short explanation per fix.

            Return your answer in **JSON format** like:
            {{
            "error_analysis": [
                {{
                "error": "...",
                "cause": "...",
                "fix": "...",
                "params_to_adjust": {{"param_name": "new_value"}}
                }}
            ]
            }}
            """

                # Call LLM to output repair suggestions
                debug_result = self.react_framework.run_react_cycle(
                    initial_prompt=debug_prompt,
                    available_tools=available_tools,
                    max_steps=2,
                    temperature=0.2
                )

                print("\n[DEBUG] LLM Debug Assistant Result:")
                print(debug_result.get("final_answer", ""))

                # Save repair suggestions to the main results
                react_result["error_fix_suggestions"] = debug_result.get("final_answer", "")
                # Write files for manual viewing
                with open("logs/error_fix_suggestions.json", "w") as f:
                    f.write(debug_result.get("final_answer", ""))
            print(f"\n=== ReAct Cycle Completed ===")
            print(f"Completed steps: {react_result.get('completed_steps', 0)}/{react_result.get('max_steps', 8)}")
            print(f"Final Answer: {react_result['final_answer']}")
            
            configs = self._parse_react_final_answer(react_result["final_answer"], stage)

            if react_result.get('reasoning_history'):
                print(f"\n=== Reasoning History ({len(react_result['reasoning_history'])} steps) ===")
                for step in react_result['reasoning_history']:
                    print(f"Step {step['step']}: {step.get('thought', 'No thought')}")
            
            print(f"Returning config for stage '{stage}': {configs}")
            return configs

        except Exception as e:
            print(f"Error in LLM call for stage {stage}: {e}")
            default_config = {
                'inspect': {"n_clusters": 5, "correlation_threshold": 0.5},
                'model': {"kernel_type": "matern", "preprocessing": "robust", 
                        "acquisition": "ei", "surrogate_weight": 0.8},
                'agglomerate': {"method": "hybrid", "quality_weight": 0.7, 
                            "uncertainty_bonus": 0.2}
            }
            return default_config.get(stage, {})
    

    def _generate_react_prompt(self, stage: str, data: Dict[str, Any]) -> str:
        """generate prompts of ReAct framework"""
        
        stage_descriptions = {
            'inspect': (
                "You are an expert EDA optimization analyst. Analyze the optimization run data to identify patterns "
                "and insights. Use the available tools to examine data distributions, correlations, and successful "
                "parameter ranges. Your goal is to understand what makes runs successful and provide recommendations "
                "for the modeling stage."
            ),
            'model': (
                "You are an expert machine learning engineer for EDA optimization. Based on the inspection results, "
                "configure the modeling approach for Bayesian optimization. Consider kernel selection, acquisition "
                "functions, and surrogate modeling strategies. Balance exploration and exploitation based on the data."
            ),
            'agglomerate': (
                "You are an expert parameter optimization specialist. Generate new parameter combinations for the "
                "next optimization iteration. Use insights from previous stages to focus on promising regions while "
                "maintaining diversity. Ensure all parameters satisfy the domain constraints."
            )
        }
        
        constraints_text = "Parameter Constraints:\n"
        for param, info in self.param_constraints.items():
            constraints_text += f"- {param} ({info['type']}, range: {info['range']})\n"
        
        react_format_instructions = """
**ReAct Framework Instructions - MUST FOLLOW THIS FORMAT:**

1. **Thought**: Analyze the current situation and decide what to do next
2. **Action**: Choose one tool from the available tools
3. **Action Input**: Provide the appropriate input for the chosen tool
4. **Observation**: Wait for the tool's response, then continue reasoning

**Available Tools**: You have access to various analysis tools. Use them to gather information before making decisions.

**DO NOT include Final Answer until you have completed all necessary analysis.**
**DO NOT predict or simulate tool observations.**
**You will receive actual Observation from tools before continuing.**

Only after proper analysis:
**Final Answer Format**: Only when you have completed your analysis, provide:
Final Answer: {your_configuration_here}

**Example**:
Thought: I need to understand the data patterns first. Let me analyze the success rates.
Action: analyze_data_patterns
Action Input: {}
Observation: [Tool response...]
Thought: Now I need to check parameter correlations...
Action: analyze_correlations
Action Input: {}
Observation: [Tool response...]
Final Answer: {"n_clusters": 5, "correlation_threshold": 0.7}
"""
        
        prompt = f"""
    {stage_descriptions[stage]}

    **Current Stage**: {stage.upper()}
    **Objective**: {self.objective}
    **Platform**: {self.platform}
    **Design**: {self.design}

    **Available Data**:
    - Total runs: {data.get('log_data', {}).get('summary', {}).get('total_runs', 0)}
    - Successful runs: {data.get('log_data', {}).get('summary', {}).get('successful_runs', 0)}
    - Failed runs: {data.get('log_data', {}).get('summary', {}).get('failed_runs', 0)}

    {constraints_text}
    {react_format_instructions}

    Begin your analysis:
    """
        
        rag_context = ""
        # ======== extract errors ========
        error_summary = self._collect_recent_errors(data)
        if error_summary and "No errors" not in error_summary:
            print("[DEBUG] RAG: Detected error summary, adding error analysis prompt...")
            prompt += f"""

        ### Detected Run Errors
        {error_summary}

        You are now acting as an **EDA Debugging Assistant**.
        Analyze the errors above and:
        1. Identify the root causes.
        2. Suggest specific parameter changes.
        3. Indicate whether the error is due to timing, routing, or constraints.
        4. Provide short explanations for each.

        Output format:
        Error Diagnosis:
        - Root Cause: ...
        - Recommended Fix: ...
        - Suggested Parameter Change: ...
        - Reason: ...
        """
        else:
            print("[DEBUG] No errors found in logs for this stage.")
        if self.rag_model is not None and self.rag_embeddings is not None:
            try:
                print("[DEBUG] RAG: Starting retrieval...")
                query = (
                    f"Stage: {stage}. Objective: {self.objective}. "
                    f"Focus on analyzing {stage}-related optimization results. "
                    f"Important metrics include wirelength, timing, area, and success rate. "
                    f"Find relevant OpenROAD documentation, parameter tuning guides, and failure pattern examples."
                )
                rag_context = answerWithRAG(
                    query,
                    self.rag_embeddings,
                    self.rag_model,
                    self.rag_docs,
                    self.rag_docsDict
                )
                print(f"[DEBUG] RAG: Retrieved context length = {len(rag_context)}")
                if rag_context.strip():
                    prompt += (
                        "\n\n=== Retrieved OpenROAD Documentation (via RAG) ===\n"
                        f"{rag_context}\n"
                        "=============================================="
                    )
                    print("[DEBUG] RAG: Context successfully added to prompt.")
                else:
                    print("[DEBUG] RAG: Empty context retrieved.")
            except Exception as e:
                prompt += f"\n\n[WARN] RAG retrieval failed: {e}"

        return prompt
    
    def _parse_react_final_answer(self, final_answer: str, stage: str) -> Dict[str, Any]:
        """parse react final answer"""
        
        default_configs = {
            'inspect': {"n_clusters": 5, "correlation_threshold": 0.5},
            'model': {"kernel_type": "matern", "preprocessing": "robust", 
                    "acquisition": "ei", "surrogate_weight": 0.8},
            'selection': {"method": "hybrid", "quality_weight": 0.7, 
                        "uncertainty_bonus": 0.2}
        }
        
        configs = {}
        
        if final_answer and "Reached maximum steps" not in final_answer:
            try:
                json_match = re.search(r'\{.*\}', final_answer, re.DOTALL)
                if json_match:
                    extracted_config = json.loads(json_match.group())
                    configs[stage] = extracted_config
                    print(f"✓ Extracted configuration from ReAct response: {extracted_config}")
                else:
                    configs[stage] = default_configs.get(stage, {})
                    print(f"⚠ Using default configuration for {stage} stage")
            except Exception as e:
                print(f"Error parsing ReAct final answer: {e}")
                configs[stage] = default_configs.get(stage, {})
        else:
            configs[stage] = default_configs.get(stage, {})
            print(f"ReAct failed to produce answer, using default for {stage}")
        
        return configs

    def run_iteration(self, num_runs: int) -> None:
        """Run a complete iteration of the optimization workflow using react framework"""
        print(f"\n=== Starting optimization iteration for {self.platform}/{self.design} ===")
        print(f"Objective: {self.objective}")
        print(f"Number of runs requested: {num_runs}")
        
        # Step 1: Inspect logs
        print("\nStep 1: Inspecting logs...")
        log_data = self.inspect_logs()
        print(f"Found {log_data['summary']['total_runs']} total runs, "
              f"{log_data['summary']['successful_runs']} successful")
        
        # Get LLM recommendations for inspection and analysis
        # print("\nGetting LLM recommendations for inspection...")
        print("\nGetting LLM recommendations with ReAct framework for inspection...")
        inspect_configs = self._call_llm('inspect', {
            'log_data': log_data,
            'initial_params': self.initial_params,
            'sdc_context': self.sdc_context
        })
        inspection_config = inspect_configs.get('inspect', {})
        print(f"React inspection config: {inspection_config}")
        
        # Step 2: Analyze metrics with LLM config
        print("\nStep 2: Analyzing metrics ...")
        metrics = self.analyze_metrics(
            log_data, 
            # n_clusters=inspect_configs['inspection']['n_clusters'],
            n_clusters=inspection_config.get('n_clusters', 5),
            # correlation_threshold=inspect_configs['inspection']['correlation_threshold']
            correlation_threshold=inspection_config.get('correlation_threshold', 0.5)
        )
        print(f"Processed metrics for {len(metrics.get('objectives', []))} successful runs")
        
        # Get LLM recommendations for modeling based on inspection results with ReAct framework
        print("\nGetting LLM recommendations with ReAct framework for modeling...")
        model_configs = self._call_llm('model', {
            'log_data': log_data,
            'metrics': metrics,
            'initial_params': self.initial_params,
            'sdc_context': self.sdc_context,
            'inspection_results': inspect_configs
        })
        model_config = model_configs.get('model', {})
        print(f"LLM model config: {model_config}")
        
        # Step 3: Evaluate models with LLM config
        print("\nStep 3: Evaluating models...")
        model_results = self.evaluate_models(
            log_data, metrics,
            # kernel_type=model_configs['model']['kernel_type'],
            model_config.get('kernel_type', 'matern'),
            # preprocessing=model_configs['model']['preprocessing'],
            preprocessing=model_config.get('preprocessing', 'robust'),
            # acquisition=model_configs['model']['acquisition'],
            acquisition=model_config.get('acquisition', 'ei'),
            # surrogate_weight=model_configs['model']['surrogate_weight']
            surrogate_weight=model_config.get('surrogate_weight', 0.8)
        )
        
        # Get LLM recommendations for parameter selection based on all previous results with ReAct framework
        print("\nGetting LLM recommendations with ReAct framework for parameter selection...")
        selection_configs = self._call_llm('agglomerate', {
            'log_data': log_data,
            'metrics': metrics,
            'model_results': model_results,
            'initial_params': self.initial_params,
            'sdc_context': self.sdc_context,
            'inspection_results': inspect_configs,
            'model_configs': model_configs
        })
        selection_config = selection_configs.get('agglomerate', {})
        print(f"LLM selection config: {selection_config}")
        
        # Step 4: Generate parameters with LLM config
        print("\nStep 4: Generating parameters...")
        self.generate_parameters(
            log_data, metrics, model_results, num_runs,
            # selection_method=selection_configs['selection']['method'],
            # quality_weight=selection_configs['selection']['quality_weight'],
            # uncertainty_bonus=selection_configs['selection']['uncertainty_bonus']
            selection_method=selection_config.get('method', 'hybrid'),
            quality_weight=selection_config.get('quality_weight', 0.7),
            uncertainty_bonus=selection_config.get('uncertainty_bonus', 0.2)
        )
 
    def inspect_logs(self) -> Dict[str, Any]:
        """Step 1: Inspect all .log and .json logs recursively"""
        log_dir = "logs"
        pattern = f"{self.platform}_{self.design}_run"
        
        log_data = {
            'runs': [],
            'summary': {
                'total_runs': 0,
                'successful_runs': 0,
                'failed_runs': 0
            }
        }

        if not os.path.exists(log_dir):
            return log_data

        run_groups = {}

        for root, _, files in os.walk(log_dir):
            for log_file in files:
                if log_file.endswith(('.log', '.json')):
                    log_path = os.path.join(root, log_file)

                    if log_file.startswith(pattern) or (self.platform in root and self.design in root):

                        run_id = "main"  
                        m = re.search(r'_run(\d+)\.log$', log_file)
                        if m:
                            run_id = f"base_{m.group(1)}"

                        elif 'base_' in root:
                            run_id = os.path.basename(root)

                        run_data = process_log_file(log_path)

                        if run_id not in run_groups:
                            run_groups[run_id] = {
                                'run_id': run_id,
                                'success': True,
                                'metrics': {},
                                'errors': [],
                                'files': []
                            }

                        run_groups[run_id]['success'] &= run_data.get('success', True)
                        run_groups[run_id]['files'].append(log_path)

                        if 'metrics' in run_data and run_data['metrics']:
                            run_groups[run_id]['metrics'].update(run_data['metrics'])

                        if 'errors' in run_data and run_data['errors']:
                            run_groups[run_id]['errors'].extend(run_data['errors'])

        for run_id, run_data in run_groups.items():
            print(f"DEBUG: Run {run_id} success: {run_data['success']}")
            print(f"DEBUG: Run {run_id} metrics: {run_data['metrics']}")
            print(f"DEBUG: Run {run_id} errors: {run_data['errors']}")
            print(f"DEBUG: Run {run_id} files: {run_data['files']}")

            log_data['runs'].append(run_data)
            log_data['summary']['total_runs'] += 1
            if run_data['success']:
                log_data['summary']['successful_runs'] += 1
            else:
                log_data['summary']['failed_runs'] += 1

        return log_data

        
    def analyze_metrics(self, log_data: Dict[str, Any], n_clusters: int, correlation_threshold: float) -> Dict[str, Any]:
        """Step 2: Analyze metrics from log data with improved analysis"""
        metrics = {
            'objectives': [],
            'surrogates': [],
            'correlations': {},
            'structure_analysis': {}
        }
        
        # Extract feature vectors and objectives
        feature_vectors = []
        objective_values = []
        surrogate_values = []
        
        for run in log_data['runs']:
            if run['success'] and 'metrics' in run:
                run_metrics = run['metrics']
                obj_values = self._calculate_objective(run)
                
                if obj_values['value'] is not None or obj_values['surrogate'] is not None:
                    # Extract parameter values as features
                    params = []
                    for param in self.parameter_names:
                        params.append(float(run.get('parameters', {}).get(param, self.initial_params.get(param, 0))))
                    feature_vectors.append(params)
                    
                    objective_values.append(obj_values['value'] if obj_values['value'] is not None else np.nan)
                    surrogate_values.append(obj_values['surrogate'] if obj_values['surrogate'] is not None else np.nan)
                    
                    # Track correlations and other metrics
                    if obj_values['value'] is not None:
                        metrics['objectives'].append(obj_values['value'])
                    if obj_values['surrogate'] is not None:
                        metrics['surrogates'].append(obj_values['surrogate'])
                    
                    if obj_values['value'] is not None and obj_values['surrogate'] is not None:
                        if 'real_vs_surrogate' not in metrics['correlations']:
                            metrics['correlations']['real_vs_surrogate'] = []
                        metrics['correlations']['real_vs_surrogate'].append({
                            'real': obj_values['value'],
                            'surrogate': obj_values['surrogate']
                        })
        
        if feature_vectors:
            X = np.array(feature_vectors)
            Y = np.array(objective_values)
            Y_surrogate = np.array(surrogate_values)
            
            # Use improved inspection functions
            metrics['distribution_analysis'] = inspect_data_distribution(X, Y, Y_surrogate)
            metrics['structure_analysis'] = inspect_data_structure(X, Y, {
                'n_clusters': n_clusters,
                'correlation_threshold': correlation_threshold
            })
            
            # Extract model recommendations if available (from new functions)
            if 'model_recommendations' in metrics['structure_analysis']:
                metrics['model_recommendations'] = metrics['structure_analysis']['model_recommendations']
            
            # Add objective-specific metrics
            if self.objective == 'ECP':
                metrics['clock_period_impact'] = {}
                for run in log_data['runs']:
                    if run['success'] and 'metrics' in run:
                        period = float(run['metrics'].get('clock_period', 0))
                        if period > 0:
                            if period not in metrics['clock_period_impact']:
                                metrics['clock_period_impact'][period] = {
                                    'final_slack': [],
                                    'cts_slack': []
                                }
                            if 'worst_slack' in run['metrics']:
                                metrics['clock_period_impact'][period]['final_slack'].append(
                                    float(run['metrics']['worst_slack']))
                            if 'cts_ws' in run['metrics']:
                                metrics['clock_period_impact'][period]['cts_slack'].append(
                                    float(run['metrics']['cts_ws']))
            
            elif self.objective == 'DWL':
                metrics['wirelength_progression'] = []
                for run in log_data['runs']:
                    if run['success'] and 'metrics' in run:
                        if 'cts_wirelength' in run['metrics'] and 'total_wirelength' in run['metrics']:
                            metrics['wirelength_progression'].append({
                                'cts': float(run['metrics']['cts_wirelength']),
                                'final': float(run['metrics']['total_wirelength'])
                            })
        
        return metrics
        

    def evaluate_models(self, log_data: Dict[str, Any], metrics: Dict[str, Any], 
                       kernel_type: str, preprocessing: str, acquisition: str, surrogate_weight: float) -> Dict[str, Any]:
        """Step 3: Use improved model functions to evaluate parameter quality"""
        model_results = {}
        
        # Build context from log data and metrics
        context = {
            'log_data': log_data,
            'metrics': metrics,
            'design_config': self.design_config,
            'initial_params': self.initial_params,
            'model_recommendations': metrics.get('model_recommendations', {})
        }
        
        # Use model recommendations if available (from new functions)
        if 'model_recommendations' in metrics:
            kernel_type = metrics['model_recommendations'].get('kernel_type', kernel_type)
            preprocessing = 'robust' if metrics['model_recommendations'].get('needs_feature_scaling', True) else 'none'
        
        # Call appropriate model functions with improved modeling
        if self.objective == 'ECP':
            model_results = evaluate_timing_model(context)
        elif self.objective == 'DWL':
            model_results = evaluate_wirelength_model(context)
        
        # Add model configuration used
        model_results['configuration'] = {
            'kernel_type': kernel_type,
            'preprocessing': preprocessing,
            'acquisition': acquisition,
            'surrogate_weight': surrogate_weight
        }
        
        return model_results
        
    def generate_parameters(self, log_data: Dict[str, Any], metrics: Dict[str, Any],
                          model_results: Dict[str, Any], num_runs: int,
                          selection_method: str = 'hybrid', quality_weight: float = 0.7,
                          uncertainty_bonus: float = 0.2, model_config: Dict[str, Any] = None) -> None:
        """Step 4: Generate parameter combinations and write to CSV"""
        # Get list of parameters to optimize from constraints
        param_names = list(self.param_constraints.keys())
        print(f"\nGenerating parameters for {len(param_names)} variables:")
        for name in param_names:
            print(f"  - {name}: {self.param_constraints[name]}")
        
        # Extract successful runs for training data
        successful_params = []
        successful_objectives = []
        for run in log_data.get('runs', []):
            if run.get('success', False) and 'metrics' in run:
                params = {}
                for param in param_names:
                    params[param] = float(run.get('parameters', {}).get(param, self.initial_params.get(param, 0)))
                successful_params.append(params)
                
                obj = self._calculate_objective(run)
                successful_objectives.append(obj['value'] if obj['value'] is not None else obj['surrogate'])
        
        print(f"Using {len(successful_params)} successful runs as training data")
        
        # Convert to numpy arrays
        if successful_params:
            X = np.array([[params[name] for name in param_names] for params in successful_params])
            y = np.array(successful_objectives)
        else:
            print("Warning: No successful runs, using initial parameters as base")
            X = np.array([[float(self.initial_params.get(name, 0)) for name in param_names]])
            y = np.array([0.0])
        
        # Get kernel type from model config
        kernel_type = model_config.get('kernel_type', 'matern') if model_config else 'matern'
        print(f"\nCreating surrogate model with {kernel_type} kernel")
        model = create_model(X, y, kernel_type=kernel_type)
        
        # Generate candidates
        n_candidates = num_runs * 10
        print(f"Generating {n_candidates} candidate points")
        candidates = latin_hypercube(n_candidates, len(param_names))
        
        # Scale candidates to parameter ranges
        for i, param in enumerate(param_names):
            constraints = self.param_constraints[param]
            min_val = float(constraints['range'][0])
            max_val = float(constraints['range'][1])
            candidates[:, i] = candidates[:, i] * (max_val - min_val) + min_val
        
        # Get predictions
        predictions, uncertainties = model.predict(candidates, return_std=True)
        
        # Select points
        print(f"\nSelecting points using {selection_method} method")
        print(f"Quality weight: {quality_weight}, Uncertainty bonus: {uncertainty_bonus}")
        quality_scores = create_quality_scores(candidates, y, predictions, uncertainties)
        selected_indices = select_points(
            candidates, quality_scores,
            method=selection_method,
            n_points=num_runs,
            config={"quality_weight": quality_weight, 
                   "uncertainty_bonus": uncertainty_bonus}
        )
        
        selected_params = candidates[selected_indices]
        
        # Validate domain constraints
        print("\nValidating domain constraints...")
        valid_params = []
        for params in selected_params:
            param_dict = {name: value for name, value in zip(param_names, params)}
            if self._validate_domain_constraints(param_dict):
                valid_params.append(param_dict)
            else:
                print("Warning: Parameter set failed domain constraints")
        
        print(f"Found {len(valid_params)} valid parameter sets out of {len(selected_params)}")
        
        # Generate more if needed
        while len(valid_params) < num_runs:
            needed = num_runs - len(valid_params)
            print(f"Generating {needed} additional parameter sets...")
            new_candidates = latin_hypercube(needed, len(param_names))
            for i, param in enumerate(param_names):
                constraints = self.param_constraints[param]
                min_val = float(constraints['range'][0])
                max_val = float(constraints['range'][1])
                new_candidates[:, i] = new_candidates[:, i] * (max_val - min_val) + min_val
            
            for params in new_candidates:
                param_dict = {name: value for name, value in zip(param_names, params)}
                if self._validate_domain_constraints(param_dict):
                    valid_params.append(param_dict)
                if len(valid_params) >= num_runs:
                    break
        
        # Write to CSV
        print(f"\nWriting {num_runs} parameter sets to CSV...")
        self._write_params_to_csv(valid_params[:num_runs])
    
    def _calculate_objective(self, run: Dict[str, Any]) -> Dict[str, float]:
        """Calculate objective value and surrogate from run metrics"""
        metrics = run.get('metrics', {})
        result = {'value': None, 'surrogate': None}
        
        if self.objective == 'ECP':
            if 'clock_period' in metrics:
                period = float(metrics['clock_period'])
                # Real ECP from final worst slack
                if 'worst_slack' in metrics:
                    result['value'] = period - float(metrics['worst_slack'])
                # Surrogate ECP from CTS worst slack
                if 'cts_ws' in metrics:
                    result['surrogate'] = period - float(metrics['cts_ws'])
                    
        elif self.objective == 'DWL':
            # Real wirelength from detailed route
            if 'total_wirelength' in metrics:
                result['value'] = float(metrics['total_wirelength'])
            # Surrogate wirelength from CTS
            if 'cts_wirelength' in metrics:
                result['surrogate'] = float(metrics['cts_wirelength'])
                
        elif self.objective == 'COMBO':
            # Get weights from environment variables
            try:
                ecp_weight = float(os.environ.get('ECP_WEIGHT'))
                wl_weight = float(os.environ.get('WL_WEIGHT'))
                ecp_weight_surrogate = float(os.environ.get('ECP_WEIGHT_SURROGATE'))
                wl_weight_surrogate = float(os.environ.get('WL_WEIGHT_SURROGATE'))
            except (ValueError, TypeError):
                raise ValueError("Weights not properly set in environment variables.")
            
            # Calculate real ECP and WL values
            ecp_value = None
            wl_value = None
            if 'clock_period' in metrics:
                clock_period = float(metrics['clock_period'])
                if 'worst_slack' in metrics:
                    ecp_value = clock_period - float(metrics['worst_slack'])
                if 'total_wirelength' in metrics:
                    wl_value = float(metrics['total_wirelength'])

            # Calculate surrogate ECP and WL values
            ecp_surrogate = None
            wl_surrogate = None
            if 'clock_period' in metrics:
                clock_period = float(metrics['clock_period'])
                if 'cts_ws' in metrics:
                    ecp_surrogate = clock_period - float(metrics['cts_ws'])
                if 'cts_wirelength' in metrics:
                    wl_surrogate = float(metrics['cts_wirelength'])

            # Calculate weighted objective for real values
            if ecp_value is not None and wl_value is not None:
                result['value'] = ecp_weight * ecp_value + wl_weight * wl_value
            elif ecp_value is not None:
                result['value'] = ecp_weight * ecp_value
            elif wl_value is not None:
                result['value'] = wl_weight * wl_value

            # Calculate weighted surrogate objective
            if ecp_surrogate is not None and wl_surrogate is not None:
                result['surrogate'] = ecp_weight_surrogate * ecp_surrogate + wl_weight_surrogate * wl_surrogate
            elif ecp_surrogate is not None:
                result['surrogate'] = ecp_weight_surrogate * ecp_surrogate
            elif wl_surrogate is not None:
                result['surrogate'] = wl_weight_surrogate * wl_surrogate

        return result
    
    def _validate_domain_constraints(self, params: Dict[str, Any]) -> bool:
        """Validate parameter combinations against domain constraints"""
        # 1. Core utilization vs cell padding
        core_util = float(params.get('core_util', 0))
        gp_pad = float(params.get('cell_pad_global', 0))
        dp_pad = float(params.get('cell_pad_detail', 0))
        
        if core_util > 80 and (gp_pad > 2 or dp_pad > 2):
            print(f"Domain constraint failed: core_util > 80 and gp_pad > 2 or dp_pad > 2")
            return False
            
        # 2. TNS end percent vs place density
        tns_end = float(params.get('tns', 0))
        place_density = float(params.get('lb_addon', 0))
        
        if tns_end < 70 and place_density > 0.7:
            print(f"Domain constraint failed: tns_end < 70 and place_density > 0.7")
            return False
            
        # 3. CTS cluster constraints
        cts_size = float(params.get('cts_size', 0))
        cts_diameter = float(params.get('cts_diameter', 0))
        
        if cts_size > 30 and cts_diameter < 100:
            print(f"Domain constraint failed: cts_size > 30 and cts_diameter < 100")
            return False
            
        return True
    
    def _write_params_to_csv(self, params_list: List[Dict[str, Any]]) -> None:
        """Write the new parameter sets to the expected CSV file for the next iteration"""
        csv_file = f"designs/{self.platform}/{self.design}/{self.platform}_{self.design}.csv"
        
        # Ensure parameters are in correct order and properly typed
        with open(csv_file, 'w', newline='\n') as f:  # Explicitly use Unix line endings
            writer = csv.writer(f)
            # Write header in correct order
            writer.writerow(self.parameter_names)
            
            # Write parameter rows
            for params in params_list:
                row = []
                for param_name in self.parameter_names:
                    value = params.get(param_name)
                    if value is None:
                        print(f"Warning: Missing value for parameter {param_name}")
                        continue
                        
                    # Apply type constraints
                    constraint = self.param_constraints[param_name]
                    param_type = constraint['type']
                    param_range = constraint['range']
                    
                    try:
                        # First convert to float for uniform handling
                        value = float(value)
                            
                        # Apply range constraints if they exist
                        if param_range is not None:
                            min_val, max_val = param_range
                            range_size = max_val - min_val
                            
                            # If value is too far out of range, resample uniformly
                            if value > max_val + range_size or value < min_val - range_size:
                                value = random.uniform(min_val, max_val)
                                print(f"Resampled {param_name} to {value} (was too far out of range)")
                            else:
                                # Otherwise just clamp to range
                                value = max(min_val, min(max_val, value))

                        # Convert to final type after range enforcement
                        if param_type == 'int':
                            value = int(round(value))
                            
                    except (ValueError, TypeError) as e:
                        print(f"Error converting {param_name} value '{value}' to {param_type}: {e}")
                        continue
                        
                    row.append(value)
                    
                if len(row) == len(self.parameter_names):
                    writer.writerow(row)
                else:
                    print(f"Warning: Skipping incomplete parameter set")
                    
        print(f"New parameter sets written to {csv_file}")

    def _parse_llm_output(self, llm_response: str) -> List[Dict[str, Any]]:
        """Parse the LLM's response and enforce parameter constraints"""
        try:
            param_sets = json.loads(llm_response)
        except json.JSONDecodeError as e:
            print(f"Error parsing LLM response: {e}")
            return []

        constrained_params = []
        for param_set in param_sets:
            ordered_params = {}
            valid = True
            for param in self.parameter_names:
                value = param_set.get(param)
                if value is None:
                    print(f"Parameter '{param}' is missing in the LLM output.")
                    valid = False
                    break
                    
                constraint = self.param_constraints.get(param)
                if constraint:
                    param_type = constraint['type']
                    param_range = constraint['range']
                    
                    try:
                        # First convert to float for uniform handling
                        value = float(value)

                        # Apply range constraints if they exist
                        if param_range is not None:
                            min_val, max_val = param_range
                            range_size = max_val - min_val
                            
                            # If value is too far out of range, resample uniformly
                            if value > max_val + range_size or value < min_val - range_size:
                                value = random.uniform(min_val, max_val)
                                print(f"Resampled {param} to {value} (was too far out of range)")
                            else:
                                # Otherwise just clamp to range
                                value = max(min_val, min(max_val, value))

                        # Convert to final type after range enforcement
                        if param_type == 'int':
                            value = int(round(value))
                        elif param_type != 'float':
                            raise ValueError(f"Unsupported parameter type: {param_type}")

                        ordered_params[param] = value
                    except (ValueError, TypeError) as e:
                        print(f"Parameter '{param}' has invalid value '{value}': {e}")
                        valid = False
                        break
                else:
                    print(f"Unknown parameter '{param}' in parameter set.")
                    valid = False
                    break
                    
            if valid and self._validate_domain_constraints(ordered_params):
                constrained_params.append(ordered_params)
            else:
                print(f"Parameter set {ordered_params} failed validation and will be discarded.")
                
        return constrained_params

    def generate_initial_parameters(self, num_runs: int) -> None:
        """Generate initial random parameters and write them to CSV using the same method as subsequent iterations"""
        params_list = []
        for _ in range(num_runs):
            params = {}
            for param in self.parameter_names:
                info = self.param_constraints[param]
                param_type = info['type']
                min_value, max_value = info['range']
                if param_type == 'int':
                    value = random.randint(int(min_value), int(max_value))
                elif param_type == 'float':
                    value = random.uniform(min_value, max_value)
                else:
                    continue  # Skip unsupported types
                params[param] = value
            params_list.append(params)

        # Use the same method to write parameters to CSV
        self._write_params_to_csv(params_list)

def main():
    if len(sys.argv) != 5:
        print("Usage: optimize.py <platform> <design> <objective> <num_runs>")
        sys.exit(1)
        
    platform = sys.argv[1]
    design = sys.argv[2]
    objective = sys.argv[3]
    num_runs = int(sys.argv[4])
    
    workflow = OptimizationWorkflow(platform, design, objective)
    workflow.run_iteration(num_runs)  # Use the run_iteration method instead of individual steps

if __name__ == "__main__":
    main() 
