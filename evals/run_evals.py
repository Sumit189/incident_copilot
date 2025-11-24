import sys
from pathlib import Path

project_root = str(Path(__file__).parent.parent.resolve())
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import os
import json
import glob
import argparse
import unittest.mock
import asyncio
import re
import time
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass


if "GITHUB_TOKEN" not in os.environ:
    os.environ["GITHUB_TOKEN"] = "mock-github-token"
if "GITHUB_REPO" not in os.environ:
    os.environ["GITHUB_REPO"] = "mock/repo"

from agents.sub_agents.incident_detection import incident_detection_agent
from agents.sub_agents.rca import rca_agent
from agents.sub_agents.solution_generator import solution_generator_agent
from tools.telemetry.factory import TelemetryFactory
from evals.mocks import MockLokiProvider, MockPrometheusProvider

from google.adk.apps import App
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.memory import InMemoryMemoryService
from google.genai import types

@dataclass
class EvalResult:
    scenario: str
    passed: bool
    stability: float
    grounding: float
    patch_safety: float
    details: str

class EvaluationRunner:
    def __init__(self, scenarios_dir: str, runs: int = 1):
        self.scenarios_dir = scenarios_dir
        self.runs = runs
        self.results: List[EvalResult] = []
        
        self._synonyms_map = {
            "connection pool": ["pool", "connection", "connectionpool", "db pool", "database pool"],
            "external api": ["external", "api", "external service", "upstream"],
            "memory leak": ["memory", "leak", "memoryleak", "resource leak"],
            "not released": ["released", "release", "freed", "deallocated"],
            "heap": ["heap space", "java heap", "memory heap"],
            "cache": ["caching", "cache management"],
            "connectivity": ["connection", "network", "network issue"]
        }

    def load_scenarios(self) -> List[Dict[str, Any]]:
        scenarios = []
        for f in glob.glob(os.path.join(self.scenarios_dir, "*.json")):
            with open(f, "r") as f_in:
                try:
                    data = json.load(f_in)
                    scenarios.extend(data if isinstance(data, list) else [data])
                except json.JSONDecodeError:
                    print(f"Error decoding {f}")
        return scenarios

    def _extract_json(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Robustly extract JSON from text, handling markdown code blocks and common formatting issues.
        """
        cleaned = text.strip()
        

        json_match = re.search(r"```(?:json)?\s*({.*?})\s*```", cleaned, re.DOTALL)
        if json_match:
            cleaned = json_match.group(1)
        

        if "{" in cleaned:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start != -1 and end != -1 and end > start:
                cleaned = cleaned[start:end+1]
        
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:

            try:
                cleaned_fixed = re.sub(r",\s*}", "}", cleaned)
                cleaned_fixed = re.sub(r",\s*]", "]", cleaned_fixed)
                return json.loads(cleaned_fixed)
            except json.JSONDecodeError:
                print(f"Invalid JSON output: {text[:500]}...")
                return None

    async def run_agent(self, agent, input_text: str, timeout: int = 180) -> Optional[Dict[str, Any]]:
        import uuid
        unique_user_id = f"eval_user_{uuid.uuid4().hex[:8]}"
        
        app = App(name="agents", root_agent=agent)
        session_service = InMemorySessionService()
        memory_service = InMemoryMemoryService()
        
        session = await session_service.create_session(
            app_name=app.name,
            user_id=unique_user_id,
        )
        
        runner = Runner(
            app=app,
            session_service=session_service,
            memory_service=memory_service,
        )
        
        content = types.Content(parts=[types.Part(text=input_text)], role="user")
        print(f"  Input: {input_text[:100]}...")
        print(f"  Starting agent execution...")
        
        responses = []
        session_id = session.id
        event_count = 0
        tool_call_count = 0
        
        try:
            async def run_agent_async():
                nonlocal event_count, tool_call_count
                function_calls_seen = []
                function_responses_seen = []
                
                async for event in runner.run_async(
                    user_id=unique_user_id,
                    session_id=session_id,
                    new_message=content,
                ):
                    event_count += 1
                    
                    try:
                        if hasattr(event, 'get_function_calls'):
                            calls = event.get_function_calls() or []
                            if calls:
                                tool_call_count += len(calls)
                                for call in calls:
                                    func_name = getattr(call, 'name', 'unknown')
                                    function_calls_seen.append(func_name)
                                    print(f"  Function call: {func_name}")
                    except Exception:
                        pass
                    
                    try:
                        if hasattr(event, 'get_function_responses'):
                            responses_list = event.get_function_responses() or []
                            if responses_list:
                                for resp in responses_list:
                                    func_name = getattr(resp, 'name', 'unknown')
                                    function_responses_seen.append(func_name)
                                    print(f"  Function response: {func_name}")
                    except Exception:
                        pass
                    
                    if hasattr(event, 'tool_calls') and event.tool_calls:
                        tool_call_count += len(event.tool_calls)
                        for tc in event.tool_calls:
                            func_name = getattr(tc, 'function_name', getattr(tc, 'name', 'unknown'))
                            function_calls_seen.append(func_name)
                            print(f"  Tool call (alt): {func_name}")
                    
                    if getattr(event, "content", None):
                        for part in event.content.parts or []:
                            if getattr(part, "text", None):
                                responses.append(part.text)
                                if len(responses) == 1:
                                    print(f"  First response chunk received")
                    
                    if event_count <= 3:
                        print(f"  Event #{event_count}: {type(event).__name__}")
                
                if event_count == 0:
                    print("  Warning: No events received from agent")
                else:
                    print(f"  Total events: {event_count}, Tool calls: {tool_call_count}, Response chunks: {len(responses)}")
                    if function_calls_seen:
                        print(f"  Function calls made: {function_calls_seen}")
                    if function_responses_seen:
                        print(f"  Function responses received: {function_responses_seen}")
            
            await asyncio.wait_for(run_agent_async(), timeout=timeout)
        except asyncio.TimeoutError:
            print(f"  ⚠️  Agent execution timed out after {timeout} seconds")
            print(f"  Partial responses received: {len(responses)} chunks")
            if event_count == 0:
                print(f"  ⚠️  No events received - agent may be stuck or rate limited")
                print(f"  💡 Tip: Check API quota/rate limits or increase delay between scenarios")
            return None
        except Exception as e:
            print(f"  ❌ Agent execution error: {e}")
            import traceback
            traceback.print_exc()
            return None
            
        full_response = "".join(responses)
        return self._extract_json(full_response)

    def _check_keywords(self, output: Dict[str, Any], keywords: List[str]) -> Tuple[bool, List[str], List[str]]:
        output_str = json.dumps(output).lower()
        found_keywords = []
        missing_keywords = []
        
        for keyword in keywords:
            keyword_lower = keyword.lower()
            found = False
            

            if keyword_lower in output_str:
                found = True

            elif keyword_lower in self._synonyms_map:
                if any(syn in output_str for syn in self._synonyms_map[keyword_lower]):
                    found = True

            elif " " in keyword_lower:
                keyword_parts = keyword_lower.split()
                if all(part in output_str for part in keyword_parts):
                    found = True
            
            if found:
                found_keywords.append(keyword)
            else:
                missing_keywords.append(keyword)
        
        total_keywords = len(keywords)
        found_count = len(found_keywords)
        

        keywords_found = len(missing_keywords) == 0
        
        if not keywords_found and total_keywords >= 3:
            if found_count >= total_keywords - 1:
                keywords_found = True
                print(f"  Partial match: Found {found_count}/{total_keywords} keywords (all but 1 - acceptable)")
        
        return keywords_found, found_keywords, missing_keywords

    async def run_detection_scenario(self, scenario: Dict[str, Any]) -> EvalResult:
        print(f"Running detection scenario: {scenario['name']}")
        
        mock_loki = MockLokiProvider(scenario["telemetry"])
        mock_prom = MockPrometheusProvider(scenario["telemetry"])
        
        print(f"  Mock setup: {len(scenario['telemetry'].get('logs', []))} logs, {len(scenario['telemetry'].get('metrics', {}))} metric types")
        
        outputs = []
        with unittest.mock.patch.object(TelemetryFactory, 'get_logs_provider', return_value=mock_loki), \
             unittest.mock.patch.object(TelemetryFactory, 'get_metrics_provider', return_value=mock_prom):
            
            for _ in range(self.runs):
                input_data = {"service_name": "test-service", "lookup_window_seconds": 300}
                output = await self.run_agent(incident_detection_agent, json.dumps(input_data))
                outputs.append(output)

        valid_outputs = [o for o in outputs if o is not None]
        if not valid_outputs:
            return EvalResult(scenario['name'], False, 0.0, 0.0, 0.0, "All runs failed")

        expected = scenario.get("expected_output", {})
        pass_count = 0
        
        for output in valid_outputs:
            expected_class = expected.get("classification")
            got_class = output.get("incident_type_hint")
            got_detected = output.get("incident_detected")
            
            if (got_class == expected_class) or \
               (expected_class == "not_incident" and not got_detected):
                pass_count += 1
            else:
                print(f"Failed run. Expected: {expected_class}, Got: {got_class} (Detected: {got_detected})")
        
        passed = pass_count == len(valid_outputs) and len(valid_outputs) > 0
        stability = len([o for o in valid_outputs if o == valid_outputs[0]]) / self.runs if self.runs > 0 else 0
        
        return EvalResult(
            scenario=scenario['name'],
            passed=passed,
            stability=stability * 100,
            grounding=100.0,
            patch_safety=0.0,
            details=f"Passed {pass_count}/{self.runs} runs"
        )

    async def run_rca_scenario(self, scenario: Dict[str, Any]) -> EvalResult:
        print(f"Running RCA scenario: {scenario['name']}")
        

        input_context = scenario.get("input_context")
        if not input_context:
            print("  ⚠️  Missing 'input_context' in scenario. RCA requires detection output.")
            return EvalResult(scenario['name'], False, 0.0, 0.0, 0.0, "Missing input_context")
            
        input_str = f"Incident Detection Agent Output: {json.dumps(input_context)}"
        
        outputs = []
        for _ in range(self.runs):
            output = await self.run_agent(rca_agent, input_str)
            outputs.append(output)

        valid_outputs = [o for o in outputs if o is not None]
        if not valid_outputs:
            return EvalResult(scenario['name'], False, 0.0, 0.0, 0.0, "All runs failed")
            
        expected = scenario.get("expected_output", {})
        pass_count = 0
        total_grounding = 0
        
        for output in valid_outputs:
            rca_keywords = expected.get("rca_keywords", [])
            keywords_found, found_keywords, missing_keywords = self._check_keywords(output, rca_keywords)
            
            if keywords_found:
                pass_count += 1
            else:
                print(f"  Missing keywords: {missing_keywords}")
                print(f"  Found keywords: {found_keywords}")
                output_preview = json.dumps(output).lower()[:300]
                print(f"  Output preview: {output_preview}...")
            

            evidence_list = []
            for rc in output.get("root_causes", []):
                evidence_list.extend(rc.get("evidence", []))
            

            input_context_str = json.dumps(input_context).lower()
            grounded_count = sum(1 for ev in evidence_list if ev.lower() in input_context_str)
            
            grounding_score = (grounded_count / len(evidence_list)) * 100 if evidence_list else 100
            total_grounding += grounding_score

        passed = pass_count == len(valid_outputs)
        stability = len([o for o in valid_outputs if o == valid_outputs[0]]) / self.runs if self.runs > 0 else 0
        avg_grounding = total_grounding / len(valid_outputs)
        
        return EvalResult(
            scenario=scenario['name'],
            passed=passed,
            stability=stability * 100,
            grounding=avg_grounding,
            patch_safety=0.0,
            details=f"Passed {pass_count}/{self.runs} runs"
        )

    async def run_patch_scenario(self, scenario: Dict[str, Any]) -> EvalResult:
        print(f"Running patch scenario: {scenario['name']}")
        
        input_context = scenario.get("input_context")
        if not input_context:
             print("  ⚠️  Missing 'input_context' in scenario.")
             return EvalResult(scenario['name'], False, 0.0, 0.0, 0.0, "Missing input_context")
        

        input_str = ""
        for key, value in input_context.items():
            input_str += f"{key}: {json.dumps(value)}\n"
        
        outputs = []
        for _ in range(self.runs):
            output = await self.run_agent(solution_generator_agent, input_str)
            outputs.append(output)
                
        valid_outputs = [o for o in outputs if o is not None]
        if not valid_outputs:
            return EvalResult(scenario['name'], False, 0.0, 0.0, 0.0, "All runs failed")
            
        expected = scenario.get("expected_output", {})
        pass_count = 0
        total_safety = 0
        
        for output in valid_outputs:
            patch = output.get("patch")
            if not patch:
                continue
                
            files_to_modify = patch.get("files_to_modify", [])
            touched_files = [f.get("path") for f in files_to_modify]
            expected_files = expected.get("files_touched", [])
            
            if set(touched_files) == set(expected_files):
                pass_count += 1
            
            patch_contains = expected.get("patch_contains", [])
            all_contained = all(any(pc in f.get("new_code_snippet", "") for f in files_to_modify) 
                              for pc in patch_contains)
            
            if all_contained:
                total_safety += 100

        passed = pass_count == len(valid_outputs)
        stability = len([o for o in valid_outputs if o == valid_outputs[0]]) / self.runs if self.runs > 0 else 0
        avg_safety = total_safety / len(valid_outputs)
        
        return EvalResult(
            scenario=scenario['name'],
            passed=passed,
            stability=stability * 100,
            grounding=100.0,
            patch_safety=avg_safety,
            details=f"Passed {pass_count}/{self.runs} runs"
        )

    async def run(self):
        scenarios = self.load_scenarios()
        print(f"Loaded {len(scenarios)} scenarios.")
        
        for idx, scenario in enumerate(scenarios, 1):
            print(f"\n[{idx}/{len(scenarios)}] Processing scenario...")
            
            sType = scenario.get("type")
            if sType == "detection":
                result = await self.run_detection_scenario(scenario)
            elif sType == "rca":
                result = await self.run_rca_scenario(scenario)
            elif sType == "patch":
                result = await self.run_patch_scenario(scenario)
            else:
                print(f"Unknown scenario type: {sType}")
                continue
            
            self.results.append(result)
            
            if idx < len(scenarios):
                print(f"  Waiting 3 seconds before next scenario...")
                await asyncio.sleep(3)
            
        self.print_report()

    def print_report(self):
        print("\n" + "="*50)
        print("EVALUATION REPORT")
        print("="*50)
        
        print("\n| Scenario Name | Status | Stability | Grounding | Patch Safety | Runs |")
        print("| :--- | :---: | :---: | :---: | :---: | :---: |")
        
        passing = 0
        for res in self.results:
            status = "✅ PASS" if res.passed else "❌ FAIL"
            if res.passed: 
                passing += 1
            
            if "Passed" in res.details:
                runs_info = res.details.split(" ")[-1]
            elif "All runs failed" in res.details:
                runs_info = f"0/{self.runs}"
            else:
                runs_info = f"0/{self.runs}"
            
            print(f"| {res.scenario} | {status} | {res.stability:.1f}% | {res.grounding:.1f}% | {res.patch_safety:.1f}% | {runs_info} |")
        
        print(f"\n**Summary: {passing}/{len(self.results)} scenarios passing**")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=1, help="Number of runs per scenario")
    args = parser.parse_args()
    
    runner = EvaluationRunner("evals/scenarios", runs=args.runs)
    asyncio.run(runner.run())
