# FP-Triage — LLM-Powered False-Positive Alert Triage

**Proof statement:** I build LLM-powered tools that auto-dismiss known-false-positive security
alerts, so a cloud team lead who gets paged at 2am can trust their queue enough to book a call
with me.

## Structure
- `src/triage_agent.py` — Checkpoint 1 MVP: reads real Azure AD interactive sign-in events,
  classifies each as dismiss/escalate via an LLM (Groq, llama-3.3-70b-versatile), writes every
  decision to a real log file.
- `BUILD_LOG.md` — build narrative: scope decisions, what broke, what changed.
- `Knowledge.txt` — documented false-positive rules and known cases from tenant analysis.
- `work/notebooks/` — weekly analysis notebooks.
- `work/data/` — real (unmodified) data exports used by the notebooks.

## Status
Checkpoint 1 (agent MVP) complete. Week 5 (model vs. baseline) in `work/notebooks/w05_model.ipynb`.
