"""Terraform plan safety gate. Usage: terraform show -json tfplan | python3 scripts/check_plan.py

Fails (exit 1) when the plan would update, replace or delete anything that is not an
Incident Memory resource, or when any planned value references another project.
"""
import json
import sys

plan = json.load(sys.stdin)
problems, summary = [], {}
for rc in plan.get("resource_changes", []):
    actions = tuple(rc["change"]["actions"])
    summary[actions] = summary.get(actions, 0) + 1
    before = rc["change"].get("before") or {}
    after = rc["change"].get("after") or {}
    blob = json.dumps([before, after]).lower()
    if "gatepath" in blob:
        problems.append(f"{rc['address']}: references another project")
    if actions in (("create",), ("no-op",), ("read",)):
        continue
    names = [str(v) for d in (before, after) for k, v in d.items()
             if k in ("name", "function_name", "bucket", "alarm_name", "role", "api_id", "rule") and v]
    # ARNs: compare the final resource segment (…:role/incident-memory-api-role -> incident-memory-api-role)
    short = [n.split("/")[-1].split(":")[-1] if n.startswith("arn:") else n for n in names]
    if not short or not all(n.startswith("incident-memory") or n == "$default" for n in short):
        problems.append(f"{rc['address']}: {'/'.join(actions)} on non-Incident-Memory resource {names}")

print("Planned actions:", {"/".join(k): v for k, v in summary.items()})
if problems:
    print("STOP. DO NOT APPLY:\n  " + "\n  ".join(problems))
    sys.exit(1)
print("OK: no changes to resources outside Incident Memory.")
