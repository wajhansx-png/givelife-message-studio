"""Offline regression runner. Model stubs are NOT a live-model quality score."""
import json,pathlib,re,subprocess,sys
root=pathlib.Path(__file__).resolve().parents[1]
suites={
 'context_and_persistence':'test_context_followthrough.py',
 'multi_step_completion':'test_one_prompt_engine.py',
 'draft_edits_and_typing':'test_draft_followups.py',
 'schedule_state_and_cancellation':'test_schedule_context.py',
 'injection_and_malformed_responses':'test_ai_architecture.py',
 'literal_routing_and_send_guards':'test_manual_sends.py',
 'draft_constraints_and_targets':'test_draft_workflow.py',
}
results=[]
for dimension,pattern in suites.items():
 run=subprocess.run([sys.executable,'scripts/qa_baseline.py',pattern],cwd=root,capture_output=True,text=True)
 summary=re.search(r'Ran (\d+) tests?',run.stderr)
 results.append({'dimension':dimension,'suite':pattern,'tests':int(summary[1]) if summary else None,'passed':run.returncode==0})
report={'mode':'offline_synthetic_state_and_stubbed_model','real_messages_sent':False,'results':results,'all_passed':all(r['passed'] for r in results)}
print(json.dumps(report,indent=2))
sys.exit(0 if report['all_passed'] else 1)
