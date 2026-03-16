

> You are a senior AI engineer. Build a complete **Agentic AI Exit Interview System** in Python using LangChain with OpenAI as the primary LLM provider and Ollama `gpt-oss:20b` as a fallback. Follow this specification exactly.
>
> ---
>
> ## Project structure
>
> Create the following file layout:
>
> ```
> exit-interview-agent/
> ├── config.py
> ├── main.py
> ├── agent/
> │   ├── __init__.py
> │   ├── interviewer.py
> │   ├── questions.py
> │   ├── decision_engine.py
> │   ├── state_manager.py
> │   ├── summarizer.py
> │   └── tools.py
> ├── storage/
> │   ├── __init__.py
> │   ├── session.py
> │   └── schema.py
> ├── outputs/
> ├── scripts/
> │   └── analyze_interviews.py
> ├── requirements.txt
> └── README.md
> ```
>
> ---
>
> ## config.py
>
> Top-level configuration file. All tunable parameters live here and are imported by other modules. No hardcoded values elsewhere.
>
> ```python
> MAX_TURNS = 15
> MAX_FOLLOWUPS_PER_QUESTION = 2
> TEMPERATURE = 0.3
> MODEL_NAME = "gpt-4o"
> SUMMARY_MODEL = "gpt-4o"
> FALLBACK_MODEL_NAME = "gpt-oss:20b"
> OUTPUT_DIR = "outputs"
> ```
>
> ---
>
> ## storage/schema.py
>
> All Pydantic v2 models. This is the single source of truth for data structure.
>
> Define these models:
>
> - `FollowUp` — `question: str`, `answer: str`
> - `ResponseEntry` — `question: str`, `answer: str`, `reason_tags: list[str]`, `sentiment: str`, `follow_ups: list[FollowUp]`
> - `AgentDecisionEntry` — `response: str`, `decision: str`, `reason: str`
> - `SummaryOutput` — `primary_exit_reason: str`, `sentiment: str`, `confidence_score: float`, `top_positives: list[str]`, `improvement_areas: list[str]`, `flag_for_hr: bool`, `flag_reason: str | None`
> - `SessionData` — `session_id: str`, `timestamp: str`, `responses: list[ResponseEntry]`, `detected_topics: list[str]`, `agent_decision_log: list[AgentDecisionEntry]`, `conversation_length: int`, `followup_count: int`, `summary: SummaryOutput | None`
>
> ---
>
> ## agent/questions.py
>
> Define a `QUESTION_BANK` list of 6 primary exit interview questions. For each question, also define a `FOLLOWUP_VARIANTS` dict mapping question index to 2–3 follow-up probes that are used when the decision engine flags a vague or shallow answer.
>
> Primary questions:
> 1. What is the primary reason for leaving the organization?
> 2. How would you describe your overall experience with the company?
> 3. What did you like most about working here?
> 4. What could the company improve?
> 5. How was your relationship with your manager and team?
> 6. Would you recommend this company to others? Why or why not?
>
> Follow-up variants should probe for specifics when answers are vague, e.g. for question 1: "Could you tell me more about what led to that decision?" and "Was there a specific event or moment that influenced your choice?"
>
> ---
>
> ## agent/state_manager.py
>
> Implement a state machine using a `InterviewState` enum with these states:
>
> ```python
> INTERVIEW_START
> ASK_QUESTION
> EVALUATE_RESPONSE
> ASK_FOLLOWUP
> NEXT_QUESTION
> INTERVIEW_COMPLETE
> GENERATE_SUMMARY
> ```
>
> The `StateManager` class tracks:
> - `current_state`
> - `current_question_index`
> - `current_followup_count`
> - `total_turns`
>
> Implement a `transition(event: str)` method that moves between states based on events: `"start"`, `"response_received"`, `"followup_needed"`, `"followup_done"`, `"next_question"`, `"all_questions_done"`, `"summary_done"`.
>
> Implement `should_terminate()` which returns `True` if any of these are true:
> - All 6 primary questions have been asked
> - `total_turns >= MAX_TURNS` from config
> - `current_followup_count >= MAX_FOLLOWUPS_PER_QUESTION` from config
>
> ---
>
> ## agent/decision_engine.py
>
> The `DecisionEngine` class is the core of agentic behavior. It receives the latest employee response and the full conversation context, makes one LLM call, and returns a structured decision.
>
> The LLM call should return a JSON object with:
>
> ```json
> {
>   "decision": "ask_followup" | "next_question",
>   "reason": "vague_answer" | "potential_management_issue" | "emotionally_charged" | "sufficient_answer" | "...",
>   "reason_tags": ["compensation", "management", "workload", "career_growth", "culture", "work_life_balance"],
>   "sentiment": "positive" | "neutral" | "negative",
>   "dominant_topics": ["compensation", "management"]
> }
> ```
>
> The class also maintains a `topic_memory: list[str]` that accumulates `dominant_topics` across all turns, deduplicating as it goes. This list maps directly to `detected_topics` in the session schema.
>
> Log every decision as an `AgentDecisionEntry` and return it alongside the decision result.
>
> Use `TEMPERATURE` from config. Keep the system prompt tightly scoped: the LLM's only job here is classification and decision-making, not conversation.
>
> ---
>
> ## agent/tools.py
>
> Define two LangChain `@tool` functions:
>
> **`classify_sentiment_and_reason(response: str) -> dict`**
> Given an employee response, return `sentiment` (positive/neutral/negative) and `reason_tags` as a list from the fixed taxonomy: `compensation`, `management`, `workload`, `career_growth`, `culture`, `work_life_balance`.
>
> **`detect_hr_flags(response: str) -> dict`**
> Given an employee response, return `{"flag": bool, "reason": str | None}`. Flag triggers on mentions of: harassment, discrimination, abusive management, unethical practices, or hostile work environment.
>
> Both tools must make their own focused LLM calls. Use `TEMPERATURE = 0` for both (classification tasks).
>
> ---
>
> ## agent/interviewer.py
>
> The `Interviewer` class manages the full conversation using `ConversationBufferMemory` from LangChain and an LLM client abstraction that uses `ChatOpenAI` first and falls back to `ChatOllama` when OpenAI is unavailable or errors.
>
> It exposes:
> - `ask(question: str) -> str` — sends a question to the employee (in demo mode, returns a pre-scripted response; in live mode, reads from stdin)
> - `get_response(employee_input: str) -> str` — processes employee input through the chain
>
> The system prompt frames the LLM as a professional, empathetic HR interviewer conducting an exit interview. It should ask one question at a time and never volunteer opinions.
>
> Support a `demo_mode: bool` flag. In demo mode, `ask()` cycles through a list of pre-scripted employee responses that cover varied sentiments and topics, including at least one management concern and one compensation mention.
>
> ---
>
> ## agent/summarizer.py
>
> The `Summarizer` class takes the complete `SessionData` object and makes a single LLM call to generate the summary.
>
> The prompt should pass the full conversation transcript (formatted as Q&A pairs), the `detected_topics` list, and the `agent_decision_log`. It should instruct the LLM to return a JSON object matching `SummaryOutput` exactly — including a `confidence_score` between 0 and 1 reflecting how clearly the exit reasons emerged from the conversation.
>
> Parse the response into a `SummaryOutput` Pydantic model and return it.
>
> ---
>
> ## storage/session.py
>
> The `SessionStore` class handles persistence. Implement:
>
> - `save(session: SessionData)` — writes `outputs/session_<id>.json`
> - `load(session_id: str) -> SessionData` — reads and parses from JSON
> - `export_transcript(session: SessionData)` — writes `outputs/session_<id>_transcript.txt` as a clean human-readable Q&A formatted text file
> - `export_summary_md(session: SessionData)` — writes `outputs/session_<id>_summary.md` as a formatted Markdown report with sections for exit reason, sentiment, improvement areas, HR flag status, and confidence score
> - `list_sessions() -> list[str]` — returns all session IDs found in the outputs directory
>
> ---
>
> ## main.py
>
> The entry point that orchestrates the full interview loop.
>
> 1. Parse a `--demo` flag from CLI args
> 2. Initialize `StateManager`, `DecisionEngine`, `Interviewer`, `SessionStore`
> 3. Create a new `SessionData` with a UUID session ID and current timestamp
> 4. Run the state machine loop:
>    - `INTERVIEW_START` → greet the employee, transition to `ASK_QUESTION`
>    - `ASK_QUESTION` → pull the current question from `QUESTION_BANK`, ask it
>    - `EVALUATE_RESPONSE` → call `DecisionEngine.evaluate()`, run `tools.classify_sentiment_and_reason()` and `tools.detect_hr_flags()`, append to session
>    - `ASK_FOLLOWUP` → ask the appropriate follow-up variant, increment `followup_count`
>    - `NEXT_QUESTION` → advance `question_index`, check `should_terminate()`
>    - `INTERVIEW_COMPLETE` → thank the employee, transition to `GENERATE_SUMMARY`
>    - `GENERATE_SUMMARY` → call `Summarizer`, attach to session, save all outputs
> 5. Print a brief completion summary to stdout using `rich`
>
> ---
>
> ## scripts/analyze_interviews.py
>
> A standalone script that reads all sessions from the outputs directory and prints an aggregate report:
> - Most common exit reasons (ranked)
> - Sentiment distribution (count of positive / neutral / negative)
> - Most common improvement areas
> - Count of HR-flagged sessions
>
> Use only `SessionStore.list_sessions()` and `SessionStore.load()` — no new LLM calls.
>
> ---
>
> ## requirements.txt
>
> Include exact versions:
> ```
> langchain>=0.2.0
> langchain-openai>=0.1.0
> langchain-ollama>=0.1.0
> openai>=1.0.0
> pydantic>=2.0.0
> python-dotenv>=1.0.0
> rich>=13.0.0
> ```
>
> ---
>
> ## README.md
>
> Write a clean README with:
> - Project overview (2–3 sentences)
> - Architecture explanation covering the state machine, decision engine, tools, and storage layers
> - Setup instructions (`pip install -r requirements.txt`, set `OPENAI_API_KEY` in `.env`, ensure Ollama is running locally, pull `gpt-oss:20b`, and optionally set `OLLAMA_BASE_URL` in `.env` for fallback mode)
> - How to run: `python main.py` (live) and `python main.py --demo` (demo mode)
> - How to run multi-interview analysis: `python scripts/analyze_interviews.py`
> - Sample output section showing a truncated example of `session_<id>_summary.md`
>
> ---
>
> ## Implementation rules
>
> - Load `OPENAI_API_KEY` and optional `OLLAMA_BASE_URL` from a `.env` file using `python-dotenv`. Default `OLLAMA_BASE_URL` to `http://localhost:11434` if unset. Never hardcode secrets.
> - All LLM calls that expect JSON responses must enforce JSON-only output via prompt instructions and use a fallback `json.loads()` parser.
> - Implement a shared LLM factory/helper so every LLM call tries OpenAI first and transparently falls back to Ollama `gpt-oss:20b` on provider failure.
> - All config values must come from `config.py` — no magic numbers anywhere else.
> - All data written to disk must be validated through Pydantic models before saving.
> - Use `rich` for all stdout output in `main.py` — no bare `print()` calls.
> - Include basic error handling around all LLM calls with a clear error message if the API call fails.
> - Write clean, well-named functions. Docstrings on every class and public method.
