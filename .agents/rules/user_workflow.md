# User Workflow Rules

## 1. Respect the Task and the Researcher's Role

Follow the user's current objective and constraints. Distinguish review, diagnosis, implementation, data recording, and scientific analysis. A review request does not authorize unrelated code or infrastructure changes. The experiment recorder records measurements and annotations; do not reintroduce automatic scientific eligibility decisions unless requested. Clearly distinguish measurement failures from judgments about whether a dataset supports a research claim.

## 2. Reason from Evidence

Separate direct observations, hypotheses, verified causes, and unresolved questions. Agree with the user or observer when the evidence supports their assessment; challenge claims when it does not. Avoid automatic agreement, automatic fault-finding, praise, and unsupported certainty. Never claim "100% valid," "definitively proven," or "production grade" from a successful command, a small example, or a mocked test alone.

## 3. Check Official Sources and the Exact Implementation

For technical claims about protocols, metrics, architecture, or compliance, consult relevant official 3GPP/ETSI specifications and primary implementation sources. Record the specification release/version and clause or table, and the repository commit, file, and function. Distinguish standardized capability, implemented capability, deployed configuration, and observed behavior. A supported feature in current upstream documentation does not prove support in the deployed version. If a source or VM is unavailable, state what remains unverified instead of guessing.

## 4. Investigate Before Changing the System

Establish expected behavior, actual behavior, affected scope, reproduction conditions, and the last known working configuration. Trace the relevant path from source measurement through transport, parsing, transformation, storage, and visualization or model input. Form a small set of plausible hypotheses and choose checks that distinguish them. Prioritize direct, low-impact checks. Prefer changing one variable at a time; when several changes are necessary, document their dependencies and rationale.

## 5. Preserve Metric Meaning and Data Provenance

For each metric used in a claim or model, identify its source, unit, direction, scope, aggregation interval, timestamp meaning, and reset behavior. Distinguish native NWDAF analytics, UPF/OAM measurements, RAN log-derived proxies, consumer-engineered features, and validation measurements. Do not silently replace missing sources or relabel adapter measurements as native analytics. State the baseline or denominator behind normalized load scores. Do not infer receiver goodput from sender rate, physical throughput from an unverified volume derivative, or integrated cell utilization from a sampled scheduler grant.

## 6. Preserve Raw Evidence

Keep original logs, API responses, timestamps, run IDs, and configuration snapshots sufficient to reproduce important findings. Preserve raw data and write derived data separately. Reports should contain focused, exact excerpts with enough context, plus a path or link to the complete evidence. Do not silently truncate relevant fields, fabricate unavailable output, expose credentials, or delete diagnostic history during routine recovery. Clearly identify evidence supplied by the user versus evidence independently inspected by the agent.

## 7. Make the Smallest Sufficient Fix

Address the demonstrated cause with a focused change. Avoid unrelated refactoring, additional services, and new scripts when existing tools can serve the purpose clearly. Preserve known working behavior and define rollback before changing a live configuration. Use the same complete configuration chain, including Compose overlays, image references, and persistent mounts, for inspection and execution. Record the effective configuration rather than assuming a template matches the running VM.

## 8. Verify Success, Failure, and Recovery

Define observable acceptance criteria before verification. Test the intended behavior and material failure paths, such as rejected commands, missing targets, invalid numbers, timeouts, and interrupted execution. For scripts, distinguish action success, readback success, and recovery success; report intentional non-recovery explicitly. Use meaningful tests proportional to the change. Label static review, mocked tests, and live validation separately. Do not claim live verification from mocks or repeat unrelated checks without a new reason.

## 9. Evaluate Research Claims Fairly

Do not tune scenarios, labels, preprocessing, or feature selection to force an expected result. Accept that a simpler model or a single-domain baseline may perform well. Check confounding, scenario fingerprints, temporal dependence, and train/test leakage before claiming causal diagnosis or generalization. Fit preprocessing on training data, preserve evaluation coverage, and use causal transformations reproducible during inference. Repeated rows within one run are not independent experimental repetitions. Explain what the available experiment can and cannot establish.

## 10. Update Documentation at the Change Checkpoint

After a significant VM, OAI, deployment, telemetry, or configuration change, update the corresponding documentation before continuing dependent work or declaring completion. During an outage, restore service first when necessary, retain investigation notes, and reconcile documentation immediately afterward. Use the repository's actual structure, including `docs/deployment/`, `docs/integration/`, `docs/telemetry/`, `docs/troubleshooting/`, and `docs/software-manifest.md`. Keep commands, configuration examples, metric definitions, and acceptance criteria consistent. Mark historical material and superseded instructions clearly.

## 11. Write Clear Technical English

Use English for repository technical documentation; communicate with the user in their preferred language. Lead with the result or problem, then explain evidence, impact, and the next action. Use concrete terms and short, connected sentences. Avoid excessive praise, inflated claims, decorative formatting, and repeated conclusions. Use tables for comparisons and numbered steps for procedures. Distinguish testbed observations from universal behavior. Notebook markdown should remain concise: title, purpose, and expected output, with additional explanation only where interpretation requires it.

## 12. Consult the Observer with a Concrete Question

For unresolved architectural, cross-domain, or methodological questions, prepare a concise brief containing: the question or decision, expected versus observed behavior, exact versions and configuration, relevant evidence, hypotheses already tested, and the proposed next step. Include alternatives and tradeoffs when they affect the decision. Do not ask the observer to approve an unspecified future implementation. Continue independently authorized work; routine fixes do not require repeated observer approval. Prepare messages for the user to forward unless direct communication is explicitly authorized.

## 13. Close Findings and Control Review Scope

Track material findings with their impact, evidence, proposed fix, and verification status. Close a finding when the relevant evidence confirms the fix. Do not reopen it without new evidence or expand every review into a new architecture audit. Report new issues separately with their scope and severity. If an out-of-scope issue remains, explain whether it blocks the current task and why. A bounded approval must identify what was reviewed and what still requires live evidence.

## 14. Commit and Push Completed Changes

For authorized repository edits, commit coherent, relevant changes after the appropriate checks, and always push newly created commits to the intended remote branch. Review the diff and staged paths first; preserve unrelated user changes. Include related documentation with the implementation. Do not force-push, commit credentials, or add bulky experiment archives indiscriminately. Track experiment evidence using appropriate repository policy and storage, with reproducible references. Report the branch, commit hash, checks performed, and push result. If pushing fails, state the failure; do not claim remote synchronization.

## 15. Report Completion Precisely

End with what changed or was found, why it matters, how it was verified, and any material remaining limitation. Name the files or components involved. When a problem remains, identify its location and a concrete next action. When no new issue is found, say so without inventing additional work. Use the term "resolved" only within the scope actually verified.
