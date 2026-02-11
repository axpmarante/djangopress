# Chat V1 Reference Guide

## Overview

Chat V1 is the original chat implementation for ZemoNotes using a **Tool Loop Architecture** with the **VEL (Verified Execution Layer)** for trustworthy AI agent actions.

### Key Features

- **Internal/Public Tag System**: LLM responses use `<internal>` tags for reasoning and VEL commands (hidden from user), and `<public>` tags for user-facing content
- **VEL Command Execution**: Structured JSON commands for CRUD operations on notes, tasks, projects, and areas
- **VEL Gate Validation**: Prevents write hallucinations by validating LLM claims against actual execution receipts
- **Two-Phase LLM Approach**: Tool loop for execution + structured summary for response validation

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                           Chat V1 Flow                               │
└─────────────────────────────────────────────────────────────────────┘

User Message
     │
     ▼
┌─────────────────┐
│  ChatService    │  chat/v1/service.py
│  send_message() │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Build Messages  │  System prompt + conversation history
│ with Context    │  chat/v1/prompts.py + chat/context.py
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        TOOL LOOP (max 10 iterations)                 │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                                                               │   │
│  │   LLM Response                                                │   │
│  │        │                                                      │   │
│  │        ▼                                                      │   │
│  │   ┌─────────────┐     YES    ┌─────────────────┐              │   │
│  │   │ Has <public>├───────────►│ Exit Loop       │              │   │
│  │   │ tag?        │            │ (final response)│              │   │
│  │   └──────┬──────┘            └─────────────────┘              │   │
│  │          │ NO                                                 │   │
│  │          ▼                                                    │   │
│  │   ┌─────────────┐     NO     ┌─────────────────┐              │   │
│  │   │ Has VEL     ├───────────►│ Continue/Break  │              │   │
│  │   │ commands?   │            │ (unexpected)    │              │   │
│  │   └──────┬──────┘            └─────────────────┘              │   │
│  │          │ YES                                                │   │
│  │          ▼                                                    │   │
│  │   ┌─────────────────┐                                         │   │
│  │   │ VEL Processor   │  vel/chat.py                            │   │
│  │   │ Parse & Execute │  vel/parser.py, vel/executor.py         │   │
│  │   └────────┬────────┘                                         │   │
│  │            │                                                  │   │
│  │            ▼                                                  │   │
│  │   ┌─────────────────┐                                         │   │
│  │   │ Inject Results  │  Format results, add to messages        │   │
│  │   │ Back to LLM     │  vel/messages.py                        │   │
│  │   └────────┬────────┘                                         │   │
│  │            │                                                  │   │
│  │            └──────────────► Next Iteration                    │   │
│  │                                                               │   │
│  └──────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────┐
│ Extract <public>│  User-facing content only
│ Content         │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      VEL GATE VALIDATION                             │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                                                               │   │
│  │   Phase 2: Structured Summary                                 │   │
│  │        │                                                      │   │
│  │        ▼                                                      │   │
│  │   LLM outputs JSON:                                           │   │
│  │   {                                                           │   │
│  │     "intent": "write",                                        │   │
│  │     "references_success": true/false,                         │   │
│  │     "message_to_user": "...",                                 │   │
│  │     "resource_ids_mentioned": [42]                            │   │
│  │   }                                                           │   │
│  │        │                                                      │   │
│  │        ▼                                                      │   │
│  │   ┌─────────────────┐                                         │   │
│  │   │ Gate Validation │  vel/gate.py                            │   │
│  │   │ Compare claims  │  Compare LLM claims vs execution        │   │
│  │   │ vs receipts     │  receipts                               │   │
│  │   └────────┬────────┘                                         │   │
│  │            │                                                  │   │
│  │            ▼                                                  │   │
│  │   Claims match receipts? ──YES──► Pass through response       │   │
│  │            │                                                  │   │
│  │            NO                                                 │   │
│  │            │                                                  │   │
│  │            ▼                                                  │   │
│  │   Override with error message                                 │   │
│  │   + Retry mechanism (max 2 retries)                           │   │
│  │                                                               │   │
│  └──────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────┐
│ Save Message    │  Store in database
│ & VEL Executions│  chat/models.py
└────────┬────────┘
         │
         ▼
   Final Response to User
```

---

## File Structure

### Chat V1 Module (`chat/v1/`)

| File | Purpose |
|------|---------|
| `__init__.py` | Exports `ChatService` |
| `service.py` | Main orchestration - `ChatService.send_message()` |
| `prompts.py` | System prompt template + `STRUCTURED_SUMMARY_PROMPT` |

### Shared Chat Components (`chat/`)

| File | Purpose |
|------|---------|
| `models.py` | `Conversation`, `Message`, `ChatVELExecution` models |
| `context.py` | `ContextBuilder` - builds user context for system prompt |
| `title_service.py` | Auto-generates conversation titles |
| `views.py` | Django views routing to V1/V2/V3/V4 |

### VEL Module (`vel/`)

| File | Purpose |
|------|---------|
| `__init__.py` | Package exports |
| `parser.py` | Parse VEL commands from text (`parse_text()`) |
| `executor.py` | Execute commands with audit logging (`Executor`, `SecureExecutor`) |
| `registry.py` | Action registration (`@action` decorator) |
| `schema.py` | Data classes (`Command`, `ExecutionResult`, `ActionSchema`) |
| `chat.py` | `VELProcessor` for chat integration |
| `messages.py` | Format results for LLM feedback |
| `gate.py` | `VELGate` for hallucination prevention |
| `permissions.py` | Permission checking, rate limiting |
| `models.py` | `AuditLog` model |
| `handlers/` | Action implementations (notes, tasks, projects, areas, search) |

---

## System Prompt Sections

The system prompt (`chat/v1/prompts.py`) is organized into 14 sections:

| # | Section | Purpose |
|---|---------|---------|
| 1 | **Core Identity** | Role as "Chief of Staff", principles (Act don't ask, Brief don't dump, etc.) |
| 2 | **The Workspace** | PARA hierarchy (Areas → Projects → Tasks/Notes), data relationships |
| 3 | **What You Know vs Fetch** | What's in context vs what needs VEL fetch |
| 4 | **Operating Modes** | Execution, Briefing, Intelligence, Capture modes |
| 5 | **Decision Logic** | 12-row decision table mapping user intent → VEL actions |
| 6 | **Communication Style** | Response formatting rules |
| 7 | **VEL Command Selection** | How to choose the right VEL command |
| 8 | **Available Actions** | Full list of VEL commands with syntax |
| 9 | **Response State Machine** | Three states: EXECUTING, ANSWERING, DONE |
| 10 | **Execution Patterns** | Single action, multi-step, search-then-act patterns |
| 11 | **VEL Gate Validation** | How responses are validated |
| 12 | **Edge Cases & Decisions** | Container selection, missing IDs, etc. |
| 13 | **Common Mistakes** | Anti-patterns to avoid |
| 14 | **Current User Context** | Dynamic context (areas, projects, recent notes, etc.) |

---

## VEL Command Format

### Syntax

Commands are embedded in `<internal>` tags using ```vel code blocks:

```
<internal>
Creating a task for the user.
```vel
{"action": "create_task", "params": {"title": "Review report", "priority": "high"}}
```
</internal>

<public>
Done! Created task #42: "Review report" with high priority.
</public>
```

### Available Actions

#### Notes
| Action | Required Params | Optional Params |
|--------|-----------------|-----------------|
| `create_note` | `title`, `content` | `container_type`, `container_id`, `tags` |
| `get_note` | `id` | - |
| `update_note` | `id` | `title`, `content`, `tags` |
| `move_note` | `id`, `container_type` | `container_id` |
| `archive_note` | `id` | - |
| `delete_note` | `id` | - |

#### Tasks
| Action | Required Params | Optional Params |
|--------|-----------------|-----------------|
| `create_task` | `title` | `description`, `priority`, `due_date`, `container_type`, `container_id` |
| `get_task` | `id` | - |
| `update_task` | `id` | `title`, `description`, `priority`, `due_date`, `status` |
| `complete_task` | `id` | - |
| `start_task` | `id` | - |
| `move_task` | `id`, `container_type` | `container_id` |
| `delete_task` | `id` | - |

#### Projects
| Action | Required Params | Optional Params |
|--------|-----------------|-----------------|
| `create_project` | `name`, `area_id` | `description`, `deadline` |
| `get_project` | `id` | - |
| `update_project` | `id` | `name`, `description`, `deadline`, `status` |
| `get_project_tasks` | `id` | `status` |
| `get_project_notes` | `id` | - |
| `archive_project` | `id` | - |

#### Areas
| Action | Required Params | Optional Params |
|--------|-----------------|-----------------|
| `create_area` | `name` | `description`, `parent_id` |
| `get_area` | `id` | - |
| `update_area` | `id` | `name`, `description` |
| `get_area_projects` | `id` | `status` |
| `get_area_notes` | `id` | - |
| `archive_area` | `id` | - |

#### Search & Lists
| Action | Required Params | Optional Params |
|--------|-----------------|-----------------|
| `search_notes` | `query` | `limit` |
| `search_all` | `query` | `limit` |
| `list_tasks` | - | `status`, `priority`, `due`, `limit` |
| `list_projects` | - | `status`, `area_id`, `limit` |
| `list_areas` | - | `limit` |
| `get_inbox` | - | `limit` |

---

## VEL Gate (Hallucination Prevention)

The VEL Gate (`vel/gate.py`) validates LLM responses against actual execution receipts.

### How It Works

1. **Phase 1**: LLM generates response with VEL commands
2. **VEL executes**: Commands are parsed and executed, generating receipts
3. **Phase 2**: LLM outputs structured JSON with claims:
   ```json
   {
     "intent": "write",
     "references_success": true,
     "message_to_user": "Created task #42",
     "resource_ids_mentioned": [42]
   }
   ```
4. **Gate validates**: Compares `references_success` against receipts
5. **Override if mismatch**: If LLM claims success but no matching receipt, response is overridden

### Gate Validation Cases

| Case | Condition | Result |
|------|-----------|--------|
| Pass through | `references_success: false` | Use LLM's message |
| Validate | `references_success: true` + matching receipt | Use LLM's message |
| Override | `references_success: true` + no receipt | Error message |
| Retry | Override triggered + no executions | Retry with correction prompt |

### Retry Mechanism (VEL Gate)

When the gate detects a write hallucination (LLM claims success but no VEL was executed):

1. Injects correction prompt: "You claimed to perform an action but no VEL was executed..."
2. Re-runs LLM with correction
3. Processes any VEL commands from the retry
4. Re-validates with gate
5. Max 2 retries before giving up

---

## VEL Error Retry (Tool Loop)

Separate from the gate retry, the tool loop has its own error recovery mechanism for VEL command failures.

### How It Works

When a VEL command fails (invalid syntax, missing params, action not found):

```
1. VEL Execution fails
   └─► Error: "Action 'create_tak' not found"

2. Error feedback injected:
   └─► [SYSTEM ERROR FEEDBACK]
       The following VEL action(s) failed:
       - Action 'create_tak' not found

       Please review and retry with corrected syntax.

3. Loop continues (doesn't exit)
   └─► LLM receives error feedback
   └─► LLM corrects: create_task (fixed typo)
   └─► VEL executes successfully
```

### Error Types Handled

| Error Type | Description | LLM Action |
|------------|-------------|------------|
| `ACTION_NOT_FOUND` | Typo in action name | Fix spelling |
| `VALIDATION_ERROR` | Missing required params | Add missing params |
| `PARSE_ERROR` | Invalid JSON syntax | Fix JSON |
| `EXECUTION_ERROR` | Handler threw exception | Adjust params |

### Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    VEL Error Retry Flow                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│   LLM emits VEL command                                      │
│        │                                                     │
│        ▼                                                     │
│   ┌─────────────┐                                            │
│   │ VEL Execute │                                            │
│   └──────┬──────┘                                            │
│          │                                                   │
│          ▼                                                   │
│   ┌──────────────┐     YES    ┌───────────────────┐          │
│   │ Has errors?  ├───────────►│ Format error      │          │
│   └──────┬───────┘            │ feedback          │          │
│          │ NO                 └─────────┬─────────┘          │
│          │                              │                    │
│          ▼                              ▼                    │
│   ┌───────────────┐           ┌───────────────────┐          │
│   │ Inject results│           │ Inject error      │          │
│   │ to LLM        │           │ to LLM            │          │
│   └───────┬───────┘           └─────────┬─────────┘          │
│           │                             │                    │
│           ▼                             ▼                    │
│   ┌───────────────┐           ┌───────────────────┐          │
│   │ Continue loop │           │ Continue loop     │          │
│   │ or exit       │           │ (LLM will retry)  │          │
│   └───────────────┘           └───────────────────┘          │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Error Feedback Template

```
[SYSTEM ERROR FEEDBACK]

The following VEL action(s) failed:
- {error_1}
- {error_2}

Please review the error(s) above and try again with corrected action syntax.
Common issues:
1. Action name might be misspelled
2. Required parameters might be missing
3. Parameter values might be in wrong format
4. The referenced resource might not exist

Please retry your response with corrected VEL commands.
```

---

## Data Flow Example

### User: "Create a task to call John tomorrow"

```
1. User message received
   └─► ChatService.send_message("Create a task to call John tomorrow")

2. Build messages with context
   └─► System prompt + user's areas/projects/tasks context

3. LLM Response (iteration 1):
   └─► <internal>
       Creating the task.
       ```vel
       {"action": "create_task", "params": {"title": "Call John", "due_date": "2025-12-21"}}
       ```
       </internal>
       <public>
       Created task #42: "Call John" due tomorrow.
       </public>

4. VEL Processing:
   └─► Parse command from ```vel block
   └─► VELProcessor.process() → Execute create_task
   └─► Result: {status: "success", result: {id: 42, title: "Call John", ...}}

5. Exit loop (has <public> tag)

6. Extract <public> content:
   └─► "Created task #42: 'Call John' due tomorrow."

7. VEL Gate Validation:
   └─► Phase 2 LLM: {references_success: true, resource_ids_mentioned: [42]}
   └─► Build receipt from execution: {status: COMMITTED, resource_id: 42}
   └─► Gate: references_success=true AND has committed receipt → PASS

8. Save to database:
   └─► Message(role="assistant", content="Created task #42...")
   └─► ChatVELExecution(action="create_task", status="success", ...)

9. Return response to user
```

---

## Key Classes

### ChatService (`chat/v1/service.py`)

```python
class ChatService:
    MAX_TOOL_ITERATIONS = 10

    def __init__(self, user, conversation):
        self.user = user
        self.conversation = conversation

    def send_message(self, user_message: str) -> dict:
        """Main entry point for processing user messages"""
        # 1. Save user message
        # 2. Build messages with system prompt
        # 3. Run tool loop
        # 4. Apply VEL gate validation
        # 5. Save assistant message and VEL executions
        # 6. Return response
```

### VELProcessor (`vel/chat.py`)

```python
class VELProcessor:
    def __init__(self, user, secure=True, session_id=None):
        self.user = user
        self.secure = secure
        self.session_id = session_id

    async def process(self, text: str) -> ProcessResult:
        """Parse and execute VEL commands from text"""
        # 1. Check for VEL commands
        # 2. Parse commands
        # 3. Execute each command
        # 4. Format results for LLM
```

### VELGate (`vel/gate.py`)

```python
class VELGate:
    def __init__(self, user):
        self.user = user

    def gate(self, structured_response, receipts, correlation_id) -> GatedResponse:
        """Validate LLM claims against execution receipts"""
        # 1. If references_success=false → pass through
        # 2. If references_success=true → check for committed receipts
        # 3. If mismatch → override with error
        # 4. If match → verify via read-after-write
```

---

## Configuration

### Model Selection

The conversation model is stored in `Conversation.model_name`. Default: `gemini-flash`.

### Debug Mode

Enable debug output in `chat/v1/service.py`:
```python
DEBUG_SERVICE = True  # Prints detailed service logs
```

---

## Common Issues & Solutions

| Issue | Cause | Solution |
|-------|-------|----------|
| "Response indicated success but no matching operation was confirmed" | LLM claimed to do something but no VEL was executed | Gate retry mechanism will try again |
| VEL command not found | Typo in action name | Check available actions in system prompt |
| Missing required params | LLM didn't provide all required parameters | VEL validates and returns error |
| Rate limit exceeded | Too many requests | Wait for reset (configured in permissions.py) |

---

## Testing

```bash
# Run all tests
python manage.py test chat

# Run VEL tests
python manage.py test vel
```

---

## Version History

- **V1 (Original)**: Tool loop + VEL Gate + internal/public tags
- **V2**: DIRECT/AGENTIC routing
- **V3**: Agentic loop
- **V4**: Multi-agent architecture
