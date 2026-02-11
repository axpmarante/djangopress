"""
Unit Tests for Chat V4 Foundation (Phase 1)

Tests cover:
- State models (ExecutionState, Plan, StepResult)
- Error handling and retry strategies
- Storage operations
- LLM client basics
"""

import json
from datetime import datetime
from django.test import TestCase, TransactionTestCase
from django.contrib.auth import get_user_model
from django.core.cache import cache

from chat.models import Conversation
from .state import (
    ExecutionState, Plan, PlanStep, StepResult,
    ExecutionStatus, StepStatus
)
from .models import ConversationState
from .storage import ExecutionStorage
from .errors import (
    ExecutionError, ErrorCategory, RetryHandler, RetryStrategy,
    V4Exception, PlanningError, StepExecutionError
)
from .llm import LLMClient, LLMResponse, TokenTracker


User = get_user_model()


class TestPlanStep(TestCase):
    """Tests for PlanStep dataclass"""

    def test_create_plan_step(self):
        """Test creating a basic plan step"""
        step = PlanStep(
            step_id=1,
            agent_type="tasks",
            action="search",
            params={"status": "pending"}
        )

        self.assertEqual(step.step_id, 1)
        self.assertEqual(step.agent_type, "tasks")
        self.assertEqual(step.action, "search")
        self.assertEqual(step.status, "pending")
        self.assertEqual(step.depends_on, [])

    def test_plan_step_serialization(self):
        """Test PlanStep to_dict and from_dict"""
        step = PlanStep(
            step_id=1,
            agent_type="notes",
            action="create",
            params={"title": "Test Note"},
            depends_on=[],
            status="completed",
            description="Create a test note"
        )

        # Serialize
        data = step.to_dict()
        self.assertEqual(data['step_id'], 1)
        self.assertEqual(data['agent_type'], "notes")

        # Deserialize
        restored = PlanStep.from_dict(data)
        self.assertEqual(restored.step_id, step.step_id)
        self.assertEqual(restored.action, step.action)
        self.assertEqual(restored.status, step.status)


class TestPlan(TestCase):
    """Tests for Plan dataclass"""

    def test_create_plan(self):
        """Test creating a plan with steps"""
        steps = [
            PlanStep(step_id=1, agent_type="tasks", action="search", params={}),
            PlanStep(step_id=2, agent_type="tasks", action="update", params={}, depends_on=[1])
        ]

        plan = Plan(
            steps=steps,
            reasoning="Search for tasks then update them",
            estimated_complexity="moderate"
        )

        self.assertEqual(len(plan.steps), 2)
        self.assertEqual(plan.estimated_complexity, "moderate")

    def test_get_pending_steps(self):
        """Test getting pending steps"""
        steps = [
            PlanStep(step_id=1, agent_type="tasks", action="search", params={}, status="completed"),
            PlanStep(step_id=2, agent_type="tasks", action="update", params={}, status="pending"),
            PlanStep(step_id=3, agent_type="tasks", action="move", params={}, status="pending")
        ]

        plan = Plan(steps=steps, reasoning="test")
        pending = plan.get_pending_steps()

        self.assertEqual(len(pending), 2)
        self.assertEqual(pending[0].step_id, 2)

    def test_get_next_executable_step(self):
        """Test getting next step with satisfied dependencies"""
        steps = [
            PlanStep(step_id=1, agent_type="tasks", action="search", params={}, status="pending"),
            PlanStep(step_id=2, agent_type="tasks", action="update", params={}, status="pending", depends_on=[1])
        ]

        plan = Plan(steps=steps, reasoning="test")

        # Step 1 has no dependencies, should be next
        next_step = plan.get_next_executable_step(set())
        self.assertEqual(next_step.step_id, 1)

        # Mark step 1 as completed, then step 2 should be next
        steps[0].status = "completed"
        next_step = plan.get_next_executable_step({1})
        self.assertEqual(next_step.step_id, 2)

    def test_plan_serialization(self):
        """Test Plan to_dict and from_dict"""
        steps = [
            PlanStep(step_id=1, agent_type="tasks", action="search", params={"query": "test"})
        ]
        plan = Plan(
            steps=steps,
            reasoning="Test plan",
            estimated_complexity="simple"
        )

        data = plan.to_dict()
        restored = Plan.from_dict(data)

        self.assertEqual(len(restored.steps), 1)
        self.assertEqual(restored.reasoning, "Test plan")


class TestStepResult(TestCase):
    """Tests for StepResult dataclass"""

    def test_create_success_result(self):
        """Test creating a successful result"""
        result = StepResult(
            step_id=1,
            agent_type="tasks",
            action="search",
            success=True,
            output={"tasks": [{"id": 1, "title": "Test"}]},
            summary="Found 1 task",
            entities_affected={"task": [1]}
        )

        self.assertTrue(result.success)
        self.assertIsNone(result.error)
        self.assertEqual(result.entities_affected, {"task": [1]})

    def test_create_error_result(self):
        """Test creating an error result"""
        result = StepResult(
            step_id=1,
            agent_type="tasks",
            action="search",
            success=False,
            output={},
            summary="",
            error="Task not found"
        )

        self.assertFalse(result.success)
        self.assertEqual(result.error, "Task not found")

    def test_step_result_serialization(self):
        """Test StepResult to_dict and from_dict"""
        result = StepResult(
            step_id=1,
            agent_type="tasks",
            action="create",
            success=True,
            output={"task_id": 42},
            summary="Created task",
            entities_affected={"task": [42]},
            tokens_used=150
        )

        data = result.to_dict()
        restored = StepResult.from_dict(data)

        self.assertEqual(restored.step_id, 1)
        self.assertTrue(restored.success)
        self.assertEqual(restored.tokens_used, 150)


class TestExecutionState(TestCase):
    """Tests for ExecutionState dataclass"""

    def test_create_execution_state(self):
        """Test creating an execution state"""
        state = ExecutionState(
            conversation_id="conv-123",
            user_id="user-456",
            user_request="Create a task"
        )

        self.assertIsNotNone(state.execution_id)
        self.assertEqual(state.status, "planning")
        self.assertEqual(state.user_request, "Create a task")

    def test_execution_state_with_plan(self):
        """Test execution state with a plan"""
        steps = [
            PlanStep(step_id=1, agent_type="tasks", action="create", params={"title": "Test"})
        ]
        plan = Plan(steps=steps, reasoning="Create task")

        state = ExecutionState(
            user_request="Create a task",
            plan=plan,
            status="stepping"
        )

        self.assertEqual(state.status, "stepping")
        self.assertIsNotNone(state.plan)
        self.assertEqual(len(state.plan.steps), 1)

    def test_get_step(self):
        """Test getting a step by ID"""
        steps = [
            PlanStep(step_id=1, agent_type="tasks", action="search", params={}),
            PlanStep(step_id=2, agent_type="tasks", action="update", params={})
        ]
        state = ExecutionState(plan=Plan(steps=steps, reasoning="test"))

        step = state.get_step(1)
        self.assertEqual(step.action, "search")

        step = state.get_step(2)
        self.assertEqual(step.action, "update")

        step = state.get_step(999)
        self.assertIsNone(step)

    def test_add_error(self):
        """Test adding errors to state"""
        state = ExecutionState()
        state.add_error("Something went wrong", step_id=1, category="validation")

        self.assertEqual(len(state.errors), 1)
        self.assertEqual(state.errors[0]['message'], "Something went wrong")
        self.assertEqual(state.errors[0]['step_id'], 1)

    def test_retry_tracking(self):
        """Test retry count tracking"""
        state = ExecutionState()

        self.assertEqual(state.get_retry_count(1), 0)

        count = state.increment_retry(1)
        self.assertEqual(count, 1)

        count = state.increment_retry(1)
        self.assertEqual(count, 2)

        self.assertEqual(state.get_retry_count(1), 2)

    def test_token_tracking(self):
        """Test token tracking"""
        state = ExecutionState()
        state.add_tokens(input_tokens=100, output_tokens=50)
        state.add_tokens(input_tokens=200, output_tokens=100)

        self.assertEqual(state.total_input_tokens, 300)
        self.assertEqual(state.total_output_tokens, 150)
        self.assertEqual(state.total_tokens, 450)

    def test_step_results_tracking(self):
        """Test tracking step results"""
        state = ExecutionState()

        result1 = StepResult(
            step_id=1, agent_type="tasks", action="search",
            success=True, output={}, summary="Found 5 tasks"
        )
        result2 = StepResult(
            step_id=2, agent_type="tasks", action="update",
            success=False, output={}, summary="", error="Failed"
        )

        state.step_results[1] = result1
        state.step_results[2] = result2

        completed = state.get_completed_results()
        self.assertEqual(len(completed), 1)

        failed = state.get_failed_results()
        self.assertEqual(len(failed), 1)

        self.assertTrue(state.has_failures())

    def test_serialization(self):
        """Test full serialization round-trip"""
        steps = [
            PlanStep(step_id=1, agent_type="tasks", action="search", params={"status": "pending"})
        ]
        plan = Plan(steps=steps, reasoning="Search tasks")

        state = ExecutionState(
            conversation_id="conv-123",
            user_id="user-456",
            user_request="Find pending tasks",
            plan=plan,
            status="stepping"
        )
        state.add_tokens(100, 50)

        # Serialize to dict
        data = state.to_dict()
        self.assertIsInstance(data, dict)

        # Restore from dict
        restored = ExecutionState.from_dict(data)
        self.assertEqual(restored.conversation_id, "conv-123")
        self.assertEqual(restored.status, "stepping")
        self.assertEqual(len(restored.plan.steps), 1)

        # JSON round-trip
        json_str = state.to_json()
        restored2 = ExecutionState.from_json(json_str)
        self.assertEqual(restored2.user_request, "Find pending tasks")


class TestExecutionErrors(TestCase):
    """Tests for error handling"""

    def test_error_from_exception_rate_limit(self):
        """Test classifying rate limit errors"""
        exc = Exception("Rate limit exceeded (429)")
        error = ExecutionError.from_exception(exc, step_id=1)

        self.assertEqual(error.category, ErrorCategory.RATE_LIMIT)
        self.assertTrue(error.retryable)
        self.assertEqual(error.step_id, 1)

    def test_error_from_exception_timeout(self):
        """Test classifying timeout errors"""
        exc = Exception("Request timed out")
        error = ExecutionError.from_exception(exc)

        self.assertEqual(error.category, ErrorCategory.TIMEOUT)
        self.assertTrue(error.retryable)

    def test_error_from_exception_not_found(self):
        """Test classifying not found errors"""
        exc = Exception("Task matching query does not exist")
        error = ExecutionError.from_exception(exc)

        self.assertEqual(error.category, ErrorCategory.NOT_FOUND)
        self.assertFalse(error.retryable)

    def test_error_from_exception_permission(self):
        """Test classifying permission errors"""
        exc = Exception("Permission denied (403)")
        error = ExecutionError.from_exception(exc)

        self.assertEqual(error.category, ErrorCategory.PERMISSION)
        self.assertFalse(error.retryable)

    def test_error_serialization(self):
        """Test error serialization"""
        error = ExecutionError(
            category=ErrorCategory.VALIDATION,
            message="Invalid input",
            step_id=1,
            retryable=True,
            suggested_action="Check data format"
        )

        data = error.to_dict()
        restored = ExecutionError.from_dict(data)

        self.assertEqual(restored.category, ErrorCategory.VALIDATION)
        self.assertEqual(restored.message, "Invalid input")


class TestRetryHandler(TestCase):
    """Tests for retry strategy determination"""

    def test_rate_limit_retry_strategy(self):
        """Test retry strategy for rate limit"""
        error = ExecutionError(
            category=ErrorCategory.RATE_LIMIT,
            message="Rate limited"
        )

        strategy = RetryHandler.get_strategy(error, retry_count=0)

        self.assertTrue(strategy.should_retry)
        self.assertEqual(strategy.wait_seconds, 5)
        self.assertTrue(strategy.reduce_batch)

    def test_max_retries_exceeded(self):
        """Test that max retries are respected"""
        error = ExecutionError(
            category=ErrorCategory.TIMEOUT,
            message="Timed out"
        )

        strategy = RetryHandler.get_strategy(error, retry_count=3)

        self.assertFalse(strategy.should_retry)

    def test_non_retryable_error(self):
        """Test non-retryable errors"""
        error = ExecutionError(
            category=ErrorCategory.NOT_FOUND,
            message="Not found"
        )

        strategy = RetryHandler.get_strategy(error, retry_count=0)

        self.assertFalse(strategy.should_retry)

    def test_should_replan(self):
        """Test replan determination"""
        error = ExecutionError(
            category=ErrorCategory.TIMEOUT,
            message="Timeout",
            retryable=True
        )

        # Should replan after max retries
        self.assertTrue(RetryHandler.should_replan(error, retry_count=3))

        # Should not replan before max retries
        self.assertFalse(RetryHandler.should_replan(error, retry_count=1))

        # NOT_FOUND should trigger replan immediately
        not_found = ExecutionError(
            category=ErrorCategory.NOT_FOUND,
            message="Not found"
        )
        self.assertTrue(RetryHandler.should_replan(not_found, retry_count=0))


class TestConversationStateModel(TransactionTestCase):
    """Tests for ConversationState Django model"""

    def setUp(self):
        """Create test user and conversation"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.conversation = Conversation.objects.create(
            user=self.user,
            title="Test Conversation",
            chat_version='v4'
        )

    def test_create_conversation_state(self):
        """Test creating conversation state"""
        state = ConversationState.objects.create(
            conversation=self.conversation,
            summary="User asked about tasks",
            topics=["tasks", "inbox"]
        )

        self.assertEqual(state.conversation, self.conversation)
        self.assertEqual(state.summary, "User asked about tasks")
        self.assertEqual(state.topics, ["tasks", "inbox"])

    def test_get_or_create_for_conversation(self):
        """Test get_or_create helper"""
        # First call creates
        state1 = ConversationState.get_or_create_for_conversation(self.conversation)
        self.assertIsNotNone(state1)

        # Second call gets existing
        state2 = ConversationState.get_or_create_for_conversation(self.conversation)
        self.assertEqual(state1.id, state2.id)

    def test_entity_tracking(self):
        """Test entity tracking methods"""
        state = ConversationState.get_or_create_for_conversation(self.conversation)

        state.update_after_execution(
            execution_summary={
                'execution_id': 'test-123',
                'request': 'Create a task',
                'outcome': 'Created task'
            },
            created_entities={'task': 42},
            affected_entities={'task': [42]}
        )

        self.assertEqual(state.get_last_created('task'), 42)
        self.assertEqual(state.get_entity_references('task'), [42])

    def test_active_execution_tracking(self):
        """Test active execution methods"""
        state = ConversationState.get_or_create_for_conversation(self.conversation)

        self.assertFalse(state.has_active_execution())

        state.set_active_execution('exec-123')
        self.assertTrue(state.has_active_execution())
        self.assertEqual(state.active_execution_id, 'exec-123')

        state.clear_active_execution()
        self.assertFalse(state.has_active_execution())


class TestExecutionStorage(TestCase):
    """Tests for ExecutionStorage"""

    def setUp(self):
        """Clear cache before each test"""
        cache.clear()

    def test_save_and_load(self):
        """Test saving and loading execution state"""
        state = ExecutionState(
            conversation_id="conv-123",
            user_request="Test request"
        )

        # Save
        ExecutionStorage.save(state)

        # Load
        loaded = ExecutionStorage.load(state.execution_id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.execution_id, state.execution_id)
        self.assertEqual(loaded.user_request, "Test request")

    def test_load_nonexistent(self):
        """Test loading nonexistent state returns None"""
        loaded = ExecutionStorage.load("nonexistent-id")
        self.assertIsNone(loaded)

    def test_delete(self):
        """Test deleting execution state"""
        state = ExecutionState()
        ExecutionStorage.save(state)

        self.assertTrue(ExecutionStorage.exists(state.execution_id))

        ExecutionStorage.delete(state.execution_id)
        self.assertFalse(ExecutionStorage.exists(state.execution_id))

    def test_update_status(self):
        """Test quick status update"""
        state = ExecutionState(status="planning")
        ExecutionStorage.save(state)

        success = ExecutionStorage.update_status(state.execution_id, "stepping")
        self.assertTrue(success)

        loaded = ExecutionStorage.load(state.execution_id)
        self.assertEqual(loaded.status, "stepping")

    def test_conversation_execution_mapping(self):
        """Test conversation to execution mapping"""
        ExecutionStorage.set_conversation_execution("conv-123", "exec-456")

        exec_id = ExecutionStorage.get_conversation_execution("conv-123")
        self.assertEqual(exec_id, "exec-456")

        ExecutionStorage.clear_conversation_execution("conv-123")
        exec_id = ExecutionStorage.get_conversation_execution("conv-123")
        self.assertIsNone(exec_id)


class TestTokenTracker(TestCase):
    """Tests for TokenTracker"""

    def test_track_tokens(self):
        """Test tracking tokens"""
        tracker = TokenTracker()

        response = LLMResponse(
            text="Test",
            input_tokens=100,
            output_tokens=50,
            model_used="claude-sonnet"
        )

        tracker.track(response, agent_type="planner")

        self.assertEqual(tracker.total_tokens, 150)
        self.assertEqual(tracker.total_input_tokens, 100)
        self.assertEqual(tracker.total_output_tokens, 50)

    def test_track_by_model(self):
        """Test tracking by model"""
        tracker = TokenTracker()

        tracker.track(LLMResponse("", 100, 50, "claude-sonnet"))
        tracker.track(LLMResponse("", 50, 25, "claude-haiku"))

        self.assertEqual(tracker.usage["claude-sonnet"]["input"], 100)
        self.assertEqual(tracker.usage["claude-haiku"]["input"], 50)

    def test_track_by_agent(self):
        """Test tracking by agent type"""
        tracker = TokenTracker()

        tracker.track(LLMResponse("", 100, 50, "claude-sonnet"), agent_type="planner")
        tracker.track(LLMResponse("", 50, 25, "claude-haiku"), agent_type="stepper")

        self.assertEqual(tracker.by_agent["planner"]["input"], 100)
        self.assertEqual(tracker.by_agent["stepper"]["input"], 50)

    def test_budget_enforcement(self):
        """Test token budget enforcement"""
        tracker = TokenTracker(budget_tokens=200)

        tracker.track(LLMResponse("", 100, 50, "claude-sonnet"))
        self.assertFalse(tracker.is_over_budget())
        self.assertEqual(tracker.remaining_budget(), 50)

        tracker.track(LLMResponse("", 50, 50, "claude-sonnet"))
        self.assertTrue(tracker.is_over_budget())

    def test_cost_estimation(self):
        """Test cost estimation"""
        tracker = TokenTracker()
        tracker.track(LLMResponse("", 1000, 500, "claude-sonnet"))

        cost = tracker.estimate_cost()
        # Should be > 0 based on cost table
        self.assertGreater(cost, 0)

    def test_summary(self):
        """Test getting usage summary"""
        tracker = TokenTracker(budget_tokens=1000)
        tracker.track(LLMResponse("", 100, 50, "claude-sonnet"), agent_type="planner")

        summary = tracker.get_summary()

        self.assertEqual(summary["total_tokens"], 150)
        self.assertEqual(summary["budget_tokens"], 1000)
        self.assertIn("by_model", summary)
        self.assertIn("by_agent", summary)
        self.assertIn("estimated_cost_usd", summary)


class TestLLMClient(TestCase):
    """Tests for LLMClient (basic tests without actual API calls)"""

    def test_model_aliases(self):
        """Test model alias mapping"""
        # Aliases map to MODEL_CONFIG keys
        client = LLMClient(model="sonnet")
        self.assertEqual(client.model_name, "claude")

        client = LLMClient(model="haiku")
        self.assertEqual(client.model_name, "gemini-lite")

        client = LLMClient(model="flash")
        self.assertEqual(client.model_name, "gemini-flash")

    def test_model_name_direct(self):
        """Test direct model_name parameter"""
        client = LLMClient(model_name="gemini-flash")
        self.assertEqual(client.model_name, "gemini-flash")

        client = LLMClient(model_name="claude")
        self.assertEqual(client.model_name, "claude")

    def test_for_conversation(self):
        """Test creating client for conversation"""
        # Create a mock conversation
        class MockConversation:
            model_name = "gpt-5.2"

        client = LLMClient.for_conversation(MockConversation())
        self.assertEqual(client.model_name, "gpt-5.2")

    def test_json_parsing(self):
        """Test JSON parsing from LLM responses"""
        client = LLMClient()

        # Plain JSON
        result = client._parse_json('{"key": "value"}')
        self.assertEqual(result, {"key": "value"})

        # JSON in code block
        result = client._parse_json('```json\n{"key": "value"}\n```')
        self.assertEqual(result, {"key": "value"})

        # JSON with surrounding text
        result = client._parse_json('Here is the result: {"key": "value"} that was it')
        self.assertEqual(result, {"key": "value"})

    def test_fix_trailing_commas(self):
        """Test fixing trailing commas"""
        client = LLMClient()

        fixed = client._fix_trailing_commas('{"a": 1,}')
        self.assertEqual(fixed, '{"a": 1}')

        fixed = client._fix_trailing_commas('[1, 2, 3,]')
        self.assertEqual(fixed, '[1, 2, 3]')


# =============================================================================
# Phase 2 Tests: Orchestration Agents
# =============================================================================

from .agents.planner import PlannerAgent, QuickPlanner
from .agents.stepper import StepperAgent, StepDecision, StepperRules
from .agents.finisher import FinisherAgent, ResponseFormatter
from .engine import ExecutionEngine, EngineResult, EngineConfig
from .retry import RetryManager, RetryConfig, BatchReducer, CircuitBreaker


class TestQuickPlanner(TestCase):
    """Tests for QuickPlanner rule-based planning"""

    def test_simple_task_creation(self):
        """Test quick planning for simple task creation"""
        plan = QuickPlanner.try_quick_plan("create a task: Review quarterly report")

        self.assertIsNotNone(plan)
        self.assertEqual(len(plan.steps), 1)
        self.assertEqual(plan.steps[0].agent_type, "tasks")
        self.assertEqual(plan.steps[0].action, "create")
        self.assertEqual(plan.steps[0].params['title'], "Review quarterly report")

    def test_simple_note_creation(self):
        """Test quick planning for simple note creation"""
        plan = QuickPlanner.try_quick_plan("create a note: Meeting notes from standup")

        self.assertIsNotNone(plan)
        self.assertEqual(len(plan.steps), 1)
        self.assertEqual(plan.steps[0].agent_type, "notes")
        self.assertEqual(plan.steps[0].action, "create")

    def test_inbox_list(self):
        """Test quick planning for inbox listing"""
        plan = QuickPlanner.try_quick_plan("show my inbox")

        self.assertIsNotNone(plan)
        self.assertEqual(plan.steps[0].agent_type, "inbox")
        self.assertEqual(plan.steps[0].action, "list")

    def test_complex_request_returns_none(self):
        """Test that complex requests don't get quick planned"""
        # Complex request that needs full planner
        plan = QuickPlanner.try_quick_plan("move all overdue tasks to my Work project")

        self.assertIsNone(plan)

    def test_ambiguous_request_returns_none(self):
        """Test that ambiguous requests don't get quick planned"""
        plan = QuickPlanner.try_quick_plan("help me organize my notes")

        self.assertIsNone(plan)


class TestPlannerAgent(TestCase):
    """Tests for PlannerAgent (without actual LLM calls)"""

    def test_parse_valid_plan(self):
        """Test parsing a valid plan response"""
        planner = PlannerAgent()

        response = {
            "understanding": "Create a task",
            "complexity": "simple",
            "steps": [
                {
                    "step_id": 1,
                    "agent_type": "tasks",
                    "action": "create",
                    "params": {"title": "Test task"},
                    "depends_on": [],
                    "description": "Create the task"
                }
            ],
            "reasoning": "Simple task creation"
        }

        plan = planner._parse_plan_response(response)

        self.assertEqual(len(plan.steps), 1)
        self.assertEqual(plan.steps[0].agent_type, "tasks")
        self.assertEqual(plan.estimated_complexity, "simple")

    def test_parse_plan_with_dependencies(self):
        """Test parsing plan with step dependencies"""
        planner = PlannerAgent()

        response = {
            "understanding": "Move tasks",
            "complexity": "moderate",
            "steps": [
                {
                    "step_id": 1,
                    "agent_type": "projects",
                    "action": "search",
                    "params": {"query": "Work"},
                    "depends_on": []
                },
                {
                    "step_id": 2,
                    "agent_type": "tasks",
                    "action": "search",
                    "params": {"filters": {"due": "overdue"}},
                    "depends_on": []
                },
                {
                    "step_id": 3,
                    "agent_type": "tasks",
                    "action": "move",
                    "params": {},
                    "depends_on": [1, 2]
                }
            ],
            "reasoning": "Need to find project and tasks first"
        }

        plan = planner._parse_plan_response(response)

        self.assertEqual(len(plan.steps), 3)
        self.assertEqual(plan.steps[2].depends_on, [1, 2])

    def test_parse_plan_invalid_dependency(self):
        """Test that invalid dependencies raise error"""
        planner = PlannerAgent()

        response = {
            "understanding": "Test",
            "steps": [
                {
                    "step_id": 1,
                    "agent_type": "tasks",
                    "action": "create",
                    "params": {},
                    "depends_on": [99]  # Invalid - step 99 doesn't exist
                }
            ]
        }

        from .errors import PlanningError
        with self.assertRaises(PlanningError):
            planner._parse_plan_response(response)

    def test_parse_plan_circular_dependency(self):
        """Test that forward dependencies raise error"""
        planner = PlannerAgent()

        response = {
            "understanding": "Test",
            "steps": [
                {
                    "step_id": 1,
                    "agent_type": "tasks",
                    "action": "search",
                    "params": {},
                    "depends_on": [2]  # Invalid - depends on later step
                },
                {
                    "step_id": 2,
                    "agent_type": "tasks",
                    "action": "update",
                    "params": {},
                    "depends_on": []
                }
            ]
        }

        from .errors import PlanningError
        with self.assertRaises(PlanningError):
            planner._parse_plan_response(response)


class TestStepperAgent(TestCase):
    """Tests for StepperAgent decision logic"""

    def setUp(self):
        """Create test execution state"""
        self.stepper = StepperAgent()

    def test_quick_decision_no_plan(self):
        """Test quick decision when no plan exists"""
        state = ExecutionState()

        decision = self.stepper._try_quick_decision(state)

        self.assertIsNotNone(decision)
        self.assertEqual(decision.action, "fail")

    def test_quick_decision_all_complete(self):
        """Test quick decision when all steps complete"""
        steps = [
            PlanStep(step_id=1, agent_type="tasks", action="search", params={}, status="completed"),
            PlanStep(step_id=2, agent_type="tasks", action="update", params={}, status="completed")
        ]
        state = ExecutionState(plan=Plan(steps=steps, reasoning="test"))

        decision = self.stepper._try_quick_decision(state)

        self.assertIsNotNone(decision)
        self.assertEqual(decision.action, "complete")

    def test_quick_decision_next_step(self):
        """Test quick decision for next executable step"""
        steps = [
            PlanStep(step_id=1, agent_type="tasks", action="search", params={}, status="pending"),
            PlanStep(step_id=2, agent_type="tasks", action="update", params={}, status="pending", depends_on=[1])
        ]
        state = ExecutionState(plan=Plan(steps=steps, reasoning="test"))

        decision = self.stepper._try_quick_decision(state)

        self.assertIsNotNone(decision)
        self.assertEqual(decision.action, "execute")
        self.assertEqual(decision.step_id, 1)

    def test_quick_decision_respects_dependencies(self):
        """Test that dependencies are respected"""
        steps = [
            PlanStep(step_id=1, agent_type="tasks", action="search", params={}, status="completed"),
            PlanStep(step_id=2, agent_type="tasks", action="update", params={}, status="pending", depends_on=[1])
        ]
        state = ExecutionState(plan=Plan(steps=steps, reasoning="test"))
        state.step_results[1] = StepResult(
            step_id=1, agent_type="tasks", action="search",
            success=True, output={}, summary="Found tasks"
        )

        decision = self.stepper._try_quick_decision(state)

        self.assertIsNotNone(decision)
        self.assertEqual(decision.action, "execute")
        self.assertEqual(decision.step_id, 2)


class TestStepperRules(TestCase):
    """Tests for StepperRules helper"""

    def test_should_retry_retryable(self):
        """Test retry decision for retryable error"""
        error = ExecutionError(
            category=ErrorCategory.TIMEOUT,
            message="Timed out",
            retryable=True
        )

        self.assertTrue(StepperRules.should_retry(error, retry_count=0))
        self.assertTrue(StepperRules.should_retry(error, retry_count=2))
        self.assertFalse(StepperRules.should_retry(error, retry_count=3))

    def test_should_retry_non_retryable(self):
        """Test retry decision for non-retryable error"""
        error = ExecutionError(
            category=ErrorCategory.NOT_FOUND,
            message="Not found",
            retryable=False
        )

        self.assertFalse(StepperRules.should_retry(error, retry_count=0))

    def test_should_replan(self):
        """Test replan decision"""
        timeout_error = ExecutionError(
            category=ErrorCategory.TIMEOUT,
            message="Timed out",
            retryable=True
        )

        not_found_error = ExecutionError(
            category=ErrorCategory.NOT_FOUND,
            message="Not found"
        )

        # Should replan after max retries
        self.assertTrue(StepperRules.should_replan(timeout_error, retry_count=3))
        self.assertFalse(StepperRules.should_replan(timeout_error, retry_count=2))

        # Should replan immediately for NOT_FOUND
        self.assertTrue(StepperRules.should_replan(not_found_error, retry_count=0))


class TestFinisherAgent(TestCase):
    """Tests for FinisherAgent (without LLM calls)"""

    def test_quick_response_single_success(self):
        """Test quick response for single successful step"""
        finisher = FinisherAgent()

        state = ExecutionState(user_request="Create a task")
        state.step_results[1] = StepResult(
            step_id=1, agent_type="tasks", action="create",
            success=True, output={}, summary="Created task 'Test'"
        )

        response = finisher._try_quick_response(state)

        self.assertIsNotNone(response)
        self.assertEqual(response, "Created task 'Test'")

    def test_quick_response_multiple_success(self):
        """Test quick response for multiple successful steps"""
        finisher = FinisherAgent()

        state = ExecutionState(user_request="Search and update")
        state.step_results[1] = StepResult(
            step_id=1, agent_type="tasks", action="search",
            success=True, output={}, summary="Found 5 tasks"
        )
        state.step_results[2] = StepResult(
            step_id=2, agent_type="tasks", action="update",
            success=True, output={}, summary="Updated 5 tasks"
        )

        response = finisher._try_quick_response(state)

        self.assertIsNotNone(response)
        self.assertIn("Found 5 tasks", response)
        self.assertIn("Updated 5 tasks", response)

    def test_quick_response_returns_none_for_complex(self):
        """Test that complex results need LLM"""
        finisher = FinisherAgent()

        state = ExecutionState(user_request="Complex request")
        # Add multiple steps with mixed results
        state.step_results[1] = StepResult(
            step_id=1, agent_type="tasks", action="search",
            success=True, output={}, summary="Found tasks"
        )
        state.step_results[2] = StepResult(
            step_id=2, agent_type="tasks", action="update",
            success=False, output={}, summary="", error="Failed"
        )

        response = finisher._try_quick_response(state)

        # Complex case with failure - needs LLM
        self.assertIsNone(response)


class TestResponseFormatter(TestCase):
    """Tests for ResponseFormatter helpers"""

    def test_format_task_list_empty(self):
        """Test formatting empty task list"""
        result = ResponseFormatter.format_task_list([])
        self.assertEqual(result, "No tasks found.")

    def test_format_task_list_few(self):
        """Test formatting few tasks"""
        tasks = [
            {"title": "Task 1", "priority": "high", "due_date": "2024-01-15"},
            {"title": "Task 2", "priority": "medium"}
        ]
        result = ResponseFormatter.format_task_list(tasks)

        self.assertIn("Task 1", result)
        self.assertIn("[high]", result)
        self.assertIn("Task 2", result)

    def test_format_task_list_many(self):
        """Test formatting many tasks"""
        tasks = [{"title": f"Task {i}"} for i in range(10)]
        result = ResponseFormatter.format_task_list(tasks)

        self.assertEqual(result, "Found 10 tasks.")

    def test_format_count(self):
        """Test count formatting"""
        self.assertEqual(
            ResponseFormatter.format_count(0, "task"),
            "You have no tasks."
        )
        self.assertEqual(
            ResponseFormatter.format_count(1, "task"),
            "You have 1 task."
        )
        self.assertEqual(
            ResponseFormatter.format_count(5, "task", "overdue"),
            "You have 5 overdue tasks."
        )

    def test_format_created(self):
        """Test creation confirmation formatting"""
        result = ResponseFormatter.format_created(
            "task", "Review report",
            {"priority": "high", "due_date": "tomorrow"}
        )

        self.assertIn("Created task 'Review report'", result)
        self.assertIn("high priority", result)


class TestExecutionEngine(TestCase):
    """Tests for ExecutionEngine (with mock agents)"""

    def setUp(self):
        """Set up test engine"""
        self.engine = ExecutionEngine(
            user_id="test-user",
            conversation_id="test-conv",
            config=EngineConfig(
                max_steps=10,
                enable_quick_planning=True
            )
        )

    def test_execute_simple_request_with_quick_plan(self):
        """Test executing a simple request using quick planning"""
        result = self.engine.execute("create a task: Test task")

        self.assertTrue(result.success)
        self.assertIsNotNone(result.execution_id)
        # Should use mock result since no real agent
        self.assertIn("Mock", result.response)

    def test_working_memory_population(self):
        """Test that working memory is populated from results"""
        state = ExecutionState()
        state.plan = Plan(
            steps=[PlanStep(step_id=1, agent_type="tasks", action="search", params={})],
            reasoning="test"
        )

        # Create mock result with tasks
        result = StepResult(
            step_id=1, agent_type="tasks", action="search",
            success=True,
            output={"tasks": [{"id": 1}, {"id": 2}, {"id": 3}]},
            summary="Found 3 tasks"
        )

        step = state.plan.steps[0]
        self.engine._update_working_memory(state, step, result)

        self.assertIn("found_tasks", state.working_memory)
        self.assertEqual(state.working_memory["found_tasks"], [1, 2, 3])

    def test_resolve_step_params_from_memory(self):
        """Test parameter resolution from working memory"""
        state = ExecutionState()
        state.working_memory["target_project_id"] = 42

        step = PlanStep(
            step_id=2,
            agent_type="tasks",
            action="move",
            params={
                "container_type": "project",
                "container_id": "memory.target_project_id"
            }
        )

        resolved = self.engine._resolve_step_params(step, state)

        self.assertEqual(resolved["container_id"], 42)


class TestRetryManager(TestCase):
    """Tests for RetryManager"""

    def test_should_retry_within_limit(self):
        """Test retry decision within limit"""
        manager = RetryManager(RetryConfig(max_retries=3))
        error = ExecutionError(category=ErrorCategory.TIMEOUT, message="", retryable=True)

        self.assertTrue(manager.should_retry(error, attempt=1))
        self.assertTrue(manager.should_retry(error, attempt=2))
        self.assertFalse(manager.should_retry(error, attempt=3))

    def test_delay_calculation(self):
        """Test exponential backoff delay"""
        manager = RetryManager(RetryConfig(
            initial_delay=1.0,
            exponential_base=2.0,
            max_delay=30.0,
            jitter=False
        ))

        self.assertEqual(manager.get_delay(1), 1.0)
        self.assertEqual(manager.get_delay(2), 2.0)
        self.assertEqual(manager.get_delay(3), 4.0)
        self.assertEqual(manager.get_delay(10), 30.0)  # Capped at max

    def test_retry_context_generation(self):
        """Test retry context generation"""
        manager = RetryManager()
        error = ExecutionError(category=ErrorCategory.RATE_LIMIT, message="Rate limited")

        context = manager.get_retry_context(error, attempt=2, original_batch_size=100)

        self.assertEqual(context.attempt, 2)
        self.assertIsNotNone(context.modification)
        self.assertEqual(context.reduced_batch_size, 50)  # Half of 100


class TestBatchReducer(TestCase):
    """Tests for BatchReducer"""

    def test_reduce_batch_size(self):
        """Test batch size reduction"""
        self.assertEqual(BatchReducer.reduce(100), 50)
        self.assertEqual(BatchReducer.reduce(10), 5)
        self.assertEqual(BatchReducer.reduce(1), 1)  # Minimum

    def test_split_batch(self):
        """Test batch splitting"""
        items = list(range(10))
        batches = BatchReducer.split_batch(items, 3)

        self.assertEqual(len(batches), 4)
        self.assertEqual(batches[0], [0, 1, 2])
        self.assertEqual(batches[-1], [9])


class TestCircuitBreaker(TestCase):
    """Tests for CircuitBreaker"""

    def test_circuit_opens_after_failures(self):
        """Test circuit opens after threshold failures"""
        breaker = CircuitBreaker(failure_threshold=3)

        self.assertTrue(breaker.can_execute())

        breaker.record_failure()
        self.assertTrue(breaker.can_execute())

        breaker.record_failure()
        self.assertTrue(breaker.can_execute())

        breaker.record_failure()
        self.assertFalse(breaker.can_execute())  # Circuit open

    def test_success_resets_circuit(self):
        """Test success resets circuit"""
        breaker = CircuitBreaker(failure_threshold=3)

        breaker.record_failure()
        breaker.record_failure()
        breaker.record_success()

        # Should be able to take more failures now
        breaker.record_failure()
        breaker.record_failure()
        self.assertTrue(breaker.can_execute())


# ============================================================================
# Phase 3 Tests - Intake & Context
# ============================================================================

from .intake import QuickClassifier, IntakeClassifier, MessageType, RouteType, IntakeResult
from .resolver import ReferenceResolver, ResolvedReference, ResolutionResult
from .context import ConversationContext, ContextBuilder, ContextCompressor, ConversationManager


class TestQuickClassifier(TestCase):
    """Tests for QuickClassifier rule-based classification"""

    def test_task_request_create(self):
        """Test classifying task creation requests"""
        result = QuickClassifier.classify("create a task: Review report")

        self.assertIsNotNone(result)
        self.assertEqual(result.message_type, MessageType.TASK_REQUEST)
        self.assertEqual(result.route, RouteType.EXECUTE)
        self.assertEqual(result.extracted_intent, 'create')

    def test_task_request_list(self):
        """Test classifying list requests"""
        result = QuickClassifier.classify("show my tasks")

        self.assertIsNotNone(result)
        self.assertEqual(result.message_type, MessageType.TASK_REQUEST)
        self.assertEqual(result.route, RouteType.EXECUTE)
        self.assertEqual(result.extracted_intent, 'list')

    def test_task_request_search(self):
        """Test classifying search requests"""
        result = QuickClassifier.classify("find notes about python")

        self.assertIsNotNone(result)
        self.assertEqual(result.message_type, MessageType.TASK_REQUEST)
        self.assertEqual(result.route, RouteType.EXECUTE)
        self.assertEqual(result.extracted_intent, 'search')

    def test_user_response_yes(self):
        """Test classifying affirmative response with active execution"""
        result = QuickClassifier.classify("yes", has_active_execution=True)

        self.assertIsNotNone(result)
        self.assertEqual(result.message_type, MessageType.USER_RESPONSE)
        self.assertEqual(result.route, RouteType.RESUME)

    def test_user_response_option_number(self):
        """Test classifying option selection with active execution"""
        result = QuickClassifier.classify("2", has_active_execution=True)

        self.assertIsNotNone(result)
        self.assertEqual(result.message_type, MessageType.USER_RESPONSE)
        self.assertEqual(result.route, RouteType.RESUME)

    def test_correction(self):
        """Test classifying corrections"""
        result = QuickClassifier.classify("no, I meant something else")

        self.assertIsNotNone(result)
        self.assertEqual(result.message_type, MessageType.CORRECTION)
        self.assertEqual(result.route, RouteType.MODIFY)

    def test_feedback(self):
        """Test classifying feedback"""
        result = QuickClassifier.classify("thanks, that's perfect!")

        self.assertIsNotNone(result)
        self.assertEqual(result.message_type, MessageType.FEEDBACK)
        self.assertEqual(result.route, RouteType.DIRECT)

    def test_question_general(self):
        """Test classifying general questions"""
        result = QuickClassifier.classify("what is the PARA method?")

        self.assertIsNotNone(result)
        self.assertEqual(result.message_type, MessageType.QUESTION)
        self.assertEqual(result.route, RouteType.DIRECT)

    def test_question_data(self):
        """Test classifying data questions (requires execution)"""
        result = QuickClassifier.classify("what tasks are due today?")

        self.assertIsNotNone(result)
        self.assertEqual(result.message_type, MessageType.TASK_REQUEST)
        self.assertEqual(result.route, RouteType.EXECUTE)

    def test_unclassifiable(self):
        """Test that ambiguous messages return None"""
        result = QuickClassifier.classify("hmm, interesting")

        self.assertIsNone(result)

    def test_entity_extraction(self):
        """Test entity extraction from messages"""
        entities = QuickClassifier._extract_entities('create a task called "Review Q4 report"')

        self.assertIn('quoted', entities)
        self.assertEqual(entities['quoted'], ['Review Q4 report'])
        self.assertIn('entity_type', entities)
        self.assertIn('task', entities['entity_type'])


class TestIntakeClassifier(TestCase):
    """Tests for IntakeClassifier (sync-only to avoid async in tests)"""

    def test_sync_classification_task(self):
        """Test sync classification of task request"""
        classifier = IntakeClassifier()
        result = classifier.classify_sync("add a new task: Test")

        self.assertEqual(result.message_type, MessageType.TASK_REQUEST)
        self.assertEqual(result.route, RouteType.EXECUTE)

    def test_sync_classification_unknown(self):
        """Test sync classification of unknown message"""
        classifier = IntakeClassifier()
        result = classifier.classify_sync("blah blah random text")

        # Should default to task request
        self.assertEqual(result.message_type, MessageType.TASK_REQUEST)
        self.assertLess(result.confidence, 0.7)


class TestReferenceResolver(TestCase):
    """Tests for ReferenceResolver"""

    def test_resolve_singular_it(self):
        """Test resolving 'it' with last created context"""
        result = ReferenceResolver.resolve(
            message="complete it",
            last_created={'task': 42}
        )

        self.assertEqual(len(result.references), 1)
        self.assertEqual(result.references[0].entity_type, 'task')
        self.assertEqual(result.references[0].entity_ids, [42])
        self.assertFalse(result.has_unresolved)

    def test_resolve_explicit_the_task(self):
        """Test resolving 'the task' reference"""
        result = ReferenceResolver.resolve(
            message="complete the task",
            last_created={'task': 15},
            last_affected={'task': [10, 11, 12]}
        )

        self.assertEqual(len(result.references), 1)
        self.assertEqual(result.references[0].entity_type, 'task')
        # Should prefer last_created over last_affected for singular
        self.assertEqual(result.references[0].entity_ids, [15])

    def test_resolve_plural_them(self):
        """Test resolving 'them' with last affected context"""
        result = ReferenceResolver.resolve(
            message="archive them",
            last_affected={'task': [1, 2, 3]}
        )

        self.assertEqual(len(result.references), 1)
        self.assertEqual(result.references[0].entity_type, 'task')
        self.assertEqual(result.references[0].entity_ids, [1, 2, 3])

    def test_resolve_with_action_context(self):
        """Test resolution uses action context hints"""
        result = ReferenceResolver.resolve(
            message="complete it",
            last_created={'note': 10},  # Note was created
            last_affected={'task': [5]}  # Task was affected
        )

        # 'complete' implies task, should resolve to task
        self.assertEqual(len(result.references), 1)
        self.assertEqual(result.references[0].entity_type, 'task')

    def test_resolve_unresolved(self):
        """Test marking unresolved references"""
        result = ReferenceResolver.resolve(
            message="delete that note",
            last_created={},
            last_affected={}
        )

        self.assertTrue(result.has_unresolved)
        self.assertIn('that note', result.unresolved_refs)

    def test_needs_resolution(self):
        """Test detecting messages that need resolution"""
        self.assertTrue(ReferenceResolver.needs_resolution("complete it"))
        self.assertTrue(ReferenceResolver.needs_resolution("move the task"))
        self.assertTrue(ReferenceResolver.needs_resolution("archive them"))
        self.assertFalse(ReferenceResolver.needs_resolution("create a task: Test"))

    def test_extract_explicit_ids(self):
        """Test extracting explicit IDs from message"""
        result = ReferenceResolver.extract_explicit_ids("complete task #42 and note 15")

        self.assertIn('task', result)
        self.assertIn(42, result['task'])
        self.assertIn('note', result)
        self.assertIn(15, result['note'])

    def test_message_annotation(self):
        """Test that resolved message is annotated"""
        result = ReferenceResolver.resolve(
            message="complete it",
            last_created={'task': 42}
        )

        self.assertIn('[task:42]', result.resolved_message)


class TestConversationContext(TestCase):
    """Tests for ConversationContext"""

    def test_get_summary_for_agent(self):
        """Test generating agent summary"""
        context = ConversationContext(
            conversation_id="test-123",
            user_id="user-1",
            summary="User is organizing work tasks",
            topics=['tasks', 'projects'],
            message_count=5,
            mentioned_entities={'task': [1, 2, 3]},
            last_created_entities={'task': 3},
            last_affected_entities={'task': [1, 2]},
            has_active_execution=False,
            active_execution_id=None,
            last_execution_summary={'request': 'create task', 'outcome': 'success'}
        )

        summary = context.get_summary_for_agent()

        self.assertIn("User is organizing work tasks", summary)
        self.assertIn("tasks", summary)
        self.assertIn("projects", summary)
        self.assertIn("create task", summary)

    def test_resolve_references(self):
        """Test context resolves references correctly"""
        context = ConversationContext(
            conversation_id="test-123",
            user_id="user-1",
            summary="",
            topics=[],
            message_count=0,
            mentioned_entities={},
            last_created_entities={'task': 42},
            last_affected_entities={},
            has_active_execution=False,
            active_execution_id=None,
            last_execution_summary=None
        )

        result = context.resolve_references("complete it")

        self.assertEqual(len(result.references), 1)
        self.assertEqual(result.references[0].entity_ids, [42])

    def test_to_dict(self):
        """Test serialization"""
        context = ConversationContext(
            conversation_id="test-123",
            user_id="user-1",
            summary="Test",
            topics=['tasks'],
            message_count=5,
            mentioned_entities={'task': [1, 2]},
            last_created_entities={'task': 2},
            last_affected_entities={'task': [1]},
            has_active_execution=True,
            active_execution_id="exec-456",
            last_execution_summary={'outcome': 'success'}
        )

        data = context.to_dict()

        self.assertEqual(data['conversation_id'], "test-123")
        self.assertEqual(data['user_id'], "user-1")
        self.assertEqual(data['has_active_execution'], True)
        self.assertEqual(data['active_execution_id'], "exec-456")


class TestContextCompressor(TestCase):
    """Tests for ContextCompressor"""

    def test_should_compress(self):
        """Test compression trigger logic"""
        # Should compress at threshold
        self.assertTrue(ContextCompressor.should_compress(10, ""))
        self.assertTrue(ContextCompressor.should_compress(20, ""))
        # Should not compress below threshold
        self.assertFalse(ContextCompressor.should_compress(5, ""))
        # Should compress if summary too long
        long_summary = "x" * 1500
        self.assertTrue(ContextCompressor.should_compress(1, long_summary))

    def test_compress_new_messages(self):
        """Test compressing new messages into summary"""
        new_messages = [
            {'role': 'user', 'content': 'create a task for project review'},
            {'role': 'assistant', 'content': 'Created task "Project review"'},
            {'role': 'user', 'content': 'now add another for budget analysis'}
        ]

        result = ContextCompressor.compress("", new_messages)

        self.assertIn("project review", result.lower())

    def test_compress_preserves_existing(self):
        """Test that existing summary is preserved"""
        existing = "User is working on Q4 planning"
        new_messages = [
            {'role': 'user', 'content': 'add a task'}
        ]

        result = ContextCompressor.compress(existing, new_messages)

        self.assertIn("Q4 planning", result)

    def test_extract_topics(self):
        """Test topic extraction from messages"""
        messages = [
            {'role': 'user', 'content': 'show my inbox'},
            {'role': 'user', 'content': 'create a task for the project'},
            {'role': 'user', 'content': 'search for notes about budgets'}
        ]

        topics = ContextCompressor.extract_topics(messages)

        self.assertIn('inbox', topics)
        self.assertIn('tasks', topics)
        self.assertIn('projects', topics)
        self.assertIn('search', topics)


class TestResolutionResult(TestCase):
    """Tests for ResolutionResult"""

    def test_get_entities_by_type(self):
        """Test getting entities by type"""
        result = ResolutionResult(
            original_message="complete it and them",
            resolved_message="complete it and them",
            references=[
                ResolvedReference("it", "task", [42], 0.9, "last_created"),
                ResolvedReference("them", "note", [1, 2, 3], 0.8, "last_affected")
            ],
            has_unresolved=False,
            unresolved_refs=[]
        )

        task_ids = result.get_entities_by_type('task')
        note_ids = result.get_entities_by_type('note')

        self.assertEqual(task_ids, [42])
        self.assertEqual(note_ids, [1, 2, 3])

    def test_to_dict(self):
        """Test serialization"""
        result = ResolutionResult(
            original_message="test",
            resolved_message="test [task:1]",
            references=[
                ResolvedReference("it", "task", [1], 0.9, "last_created")
            ],
            has_unresolved=False,
            unresolved_refs=[]
        )

        data = result.to_dict()

        self.assertEqual(data['original_message'], "test")
        self.assertEqual(len(data['references']), 1)
        self.assertEqual(data['references'][0]['entity_type'], 'task')


# ============================================================================
# Phase 4 Tests - Specialized Agents & Registry
# ============================================================================

from .agents.registry import AgentRegistry, MockAgent, register_all_agents
from .agents.tasks import TasksAgent
from .agents.notes import NotesAgent
from .agents.projects import ProjectsAgent
from .agents.areas import AreasAgent
from .agents.inbox import InboxAgent
from .agents.search import SearchAgent
from .agents.tags import TagsAgent
from .agents.journal import JournalAgent
from .agents.review import ReviewAgent
from .agents.organize import OrganizeAgent
from .agents.calendar import CalendarAgent


class TestAgentRegistry(TestCase):
    """Tests for AgentRegistry"""

    def setUp(self):
        """Ensure agents are registered"""
        # Clear and re-register for clean state
        AgentRegistry.clear()
        register_all_agents()

    def test_all_agents_registered(self):
        """Test all 11 specialized agents are registered"""
        expected_agents = [
            'tasks', 'notes', 'projects', 'areas', 'inbox',
            'search', 'tags', 'journal', 'review', 'organize', 'calendar'
        ]

        registered = AgentRegistry.list_agents()

        for agent_type in expected_agents:
            self.assertIn(agent_type, registered, f"Agent '{agent_type}' not registered")

    def test_get_agent(self):
        """Test getting agent by type"""
        agent = AgentRegistry.get('tasks')

        self.assertIsNotNone(agent)
        self.assertEqual(agent.AGENT_TYPE, 'tasks')
        self.assertIsInstance(agent, TasksAgent)

    def test_get_unknown_agent(self):
        """Test getting unknown agent returns None"""
        agent = AgentRegistry.get('unknown_agent')
        self.assertIsNone(agent)

    def test_get_or_mock(self):
        """Test get_or_mock returns mock for unknown"""
        agent = AgentRegistry.get_or_mock('unknown_agent')

        self.assertIsNotNone(agent)
        self.assertIsInstance(agent, MockAgent)

    def test_has_agent(self):
        """Test has_agent check"""
        self.assertTrue(AgentRegistry.has_agent('tasks'))
        self.assertTrue(AgentRegistry.has_agent('notes'))
        self.assertFalse(AgentRegistry.has_agent('unknown'))

    def test_get_actions(self):
        """Test getting actions for agent type"""
        actions = AgentRegistry.get_actions('tasks')

        self.assertIn('create', actions)
        self.assertIn('update', actions)
        self.assertIn('delete', actions)
        self.assertIn('list', actions)
        self.assertIn('complete', actions)

    def test_validate_action(self):
        """Test action validation"""
        self.assertTrue(AgentRegistry.validate_action('tasks', 'create'))
        self.assertTrue(AgentRegistry.validate_action('notes', 'summarize'))
        self.assertFalse(AgentRegistry.validate_action('tasks', 'invalid_action'))

    def test_get_all_actions(self):
        """Test getting all actions for all agents"""
        all_actions = AgentRegistry.get_all_actions()

        self.assertIn('tasks', all_actions)
        self.assertIn('notes', all_actions)
        self.assertIn('create', all_actions['tasks'])


class TestTasksAgentStructure(TestCase):
    """Tests for TasksAgent structure (not execution)"""

    def test_agent_type(self):
        """Test agent type is set"""
        agent = TasksAgent()
        self.assertEqual(agent.AGENT_TYPE, 'tasks')

    def test_available_actions(self):
        """Test all expected actions are available"""
        agent = TasksAgent()

        expected_actions = [
            'create', 'get', 'update', 'delete', 'list', 'search',
            'complete', 'start', 'set_waiting', 'add_subtask',
            'archive', 'unarchive'
        ]

        for action in expected_actions:
            self.assertIn(action, agent.AVAILABLE_ACTIONS)

    def test_validate_action(self):
        """Test action validation"""
        agent = TasksAgent()

        self.assertTrue(agent.validate_action('create'))
        self.assertTrue(agent.validate_action('complete'))
        self.assertFalse(agent.validate_action('invalid'))

    def test_date_parsing(self):
        """Test date parsing helper"""
        agent = TasksAgent()
        from datetime import date, timedelta

        today = date.today()

        self.assertEqual(agent._parse_date('today'), today)
        self.assertEqual(agent._parse_date('tomorrow'), today + timedelta(days=1))
        self.assertEqual(agent._parse_date('2024-01-15'), date(2024, 1, 15))
        self.assertIsNone(agent._parse_date(None))


class TestNotesAgentStructure(TestCase):
    """Tests for NotesAgent structure"""

    def test_agent_type(self):
        """Test agent type is set"""
        agent = NotesAgent()
        self.assertEqual(agent.AGENT_TYPE, 'notes')

    def test_available_actions(self):
        """Test all expected actions are available"""
        agent = NotesAgent()

        expected_actions = [
            'create', 'get', 'update', 'delete', 'list', 'search',
            'summarize', 'add_layer', 'link', 'unlink', 'get_links',
            'archive', 'add_tag', 'remove_tag'
        ]

        for action in expected_actions:
            self.assertIn(action, agent.AVAILABLE_ACTIONS)

    def test_linkage_types(self):
        """Test linkage types are defined"""
        agent = NotesAgent()

        expected_types = ['related', 'supports', 'contradicts', 'extends']

        for link_type in expected_types:
            self.assertIn(link_type, agent.LINKAGE_TYPES)


class TestProjectsAgentStructure(TestCase):
    """Tests for ProjectsAgent structure"""

    def test_agent_type(self):
        """Test agent type is set"""
        agent = ProjectsAgent()
        self.assertEqual(agent.AGENT_TYPE, 'projects')

    def test_project_and_plan_actions(self):
        """Test both project and plan actions are available"""
        agent = ProjectsAgent()

        # Project actions
        self.assertIn('create', agent.AVAILABLE_ACTIONS)
        self.assertIn('complete', agent.AVAILABLE_ACTIONS)
        self.assertIn('hold', agent.AVAILABLE_ACTIONS)
        self.assertIn('activate', agent.AVAILABLE_ACTIONS)

        # Plan actions
        self.assertIn('create_plan', agent.AVAILABLE_ACTIONS)
        self.assertIn('get_plan', agent.AVAILABLE_ACTIONS)
        self.assertIn('add_step', agent.AVAILABLE_ACTIONS)
        self.assertIn('complete_step', agent.AVAILABLE_ACTIONS)


class TestSearchAgentStructure(TestCase):
    """Tests for SearchAgent structure"""

    def test_agent_type(self):
        """Test agent type is set"""
        agent = SearchAgent()
        self.assertEqual(agent.AGENT_TYPE, 'search')

    def test_cross_entity_search_actions(self):
        """Test cross-entity search actions"""
        agent = SearchAgent()

        self.assertIn('search', agent.AVAILABLE_ACTIONS)
        self.assertIn('search_notes', agent.AVAILABLE_ACTIONS)
        self.assertIn('search_tasks', agent.AVAILABLE_ACTIONS)
        self.assertIn('search_projects', agent.AVAILABLE_ACTIONS)
        self.assertIn('search_by_tag', agent.AVAILABLE_ACTIONS)
        self.assertIn('recent', agent.AVAILABLE_ACTIONS)
        self.assertIn('due_soon', agent.AVAILABLE_ACTIONS)


class TestCalendarAgentStructure(TestCase):
    """Tests for CalendarAgent structure"""

    def test_agent_type(self):
        """Test agent type is set"""
        agent = CalendarAgent()
        self.assertEqual(agent.AGENT_TYPE, 'calendar')

    def test_calendar_actions(self):
        """Test calendar-specific actions"""
        agent = CalendarAgent()

        self.assertIn('today', agent.AVAILABLE_ACTIONS)
        self.assertIn('tomorrow', agent.AVAILABLE_ACTIONS)
        self.assertIn('this_week', agent.AVAILABLE_ACTIONS)
        self.assertIn('next_week', agent.AVAILABLE_ACTIONS)
        self.assertIn('deadlines', agent.AVAILABLE_ACTIONS)
        self.assertIn('timeline', agent.AVAILABLE_ACTIONS)
        self.assertIn('free_days', agent.AVAILABLE_ACTIONS)


class TestReviewAgentStructure(TestCase):
    """Tests for ReviewAgent structure"""

    def test_agent_type(self):
        """Test agent type is set"""
        agent = ReviewAgent()
        self.assertEqual(agent.AGENT_TYPE, 'review')

    def test_review_actions(self):
        """Test review-specific actions"""
        agent = ReviewAgent()

        self.assertIn('stale_items', agent.AVAILABLE_ACTIONS)
        self.assertIn('neglected_projects', agent.AVAILABLE_ACTIONS)
        self.assertIn('overdue_tasks', agent.AVAILABLE_ACTIONS)
        self.assertIn('cleanup_suggestions', agent.AVAILABLE_ACTIONS)
        self.assertIn('weekly_summary', agent.AVAILABLE_ACTIONS)
        self.assertIn('area_health', agent.AVAILABLE_ACTIONS)


class TestOrganizeAgentStructure(TestCase):
    """Tests for OrganizeAgent structure"""

    def test_agent_type(self):
        """Test agent type is set"""
        agent = OrganizeAgent()
        self.assertEqual(agent.AGENT_TYPE, 'organize')

    def test_organize_actions(self):
        """Test organize-specific actions"""
        agent = OrganizeAgent()

        self.assertIn('move', agent.AVAILABLE_ACTIONS)
        self.assertIn('move_bulk', agent.AVAILABLE_ACTIONS)
        self.assertIn('archive', agent.AVAILABLE_ACTIONS)
        self.assertIn('archive_bulk', agent.AVAILABLE_ACTIONS)
        self.assertIn('merge_notes', agent.AVAILABLE_ACTIONS)


class TestTagsAgentStructure(TestCase):
    """Tests for TagsAgent structure"""

    def test_agent_type(self):
        """Test agent type is set"""
        agent = TagsAgent()
        self.assertEqual(agent.AGENT_TYPE, 'tags')

    def test_tag_types(self):
        """Test tag types are defined"""
        agent = TagsAgent()

        expected_types = ['context', 'person', 'topic', 'status', 'energy', 'location']

        for tag_type in expected_types:
            self.assertIn(tag_type, agent.TAG_TYPES)

    def test_bulk_actions(self):
        """Test bulk tag actions"""
        agent = TagsAgent()

        self.assertIn('bulk_add', agent.AVAILABLE_ACTIONS)
        self.assertIn('bulk_remove', agent.AVAILABLE_ACTIONS)
        self.assertIn('merge', agent.AVAILABLE_ACTIONS)


class TestJournalAgentStructure(TestCase):
    """Tests for JournalAgent structure"""

    def test_agent_type(self):
        """Test agent type is set"""
        agent = JournalAgent()
        self.assertEqual(agent.AGENT_TYPE, 'journal')

    def test_daily_and_weekly_actions(self):
        """Test both daily and weekly journal actions"""
        agent = JournalAgent()

        # Daily actions
        self.assertIn('create_daily', agent.AVAILABLE_ACTIONS)
        self.assertIn('get_daily', agent.AVAILABLE_ACTIONS)
        self.assertIn('update_daily', agent.AVAILABLE_ACTIONS)

        # Weekly actions
        self.assertIn('create_weekly', agent.AVAILABLE_ACTIONS)
        self.assertIn('get_weekly', agent.AVAILABLE_ACTIONS)

        # Habit actions
        self.assertIn('list_habits', agent.AVAILABLE_ACTIONS)
        self.assertIn('track_habit', agent.AVAILABLE_ACTIONS)


class TestMockAgent(TestCase):
    """Tests for MockAgent"""

    def test_mock_accepts_any_action(self):
        """Test mock agent accepts any action"""
        mock = MockAgent('test_agent')

        self.assertTrue(mock.validate_action('any_action'))
        self.assertTrue(mock.validate_action('another_action'))

    def test_mock_agent_type(self):
        """Test mock agent type is set"""
        mock = MockAgent('custom_type')
        self.assertEqual(mock.AGENT_TYPE, 'custom_type')


# =============================================================================
# Phase 5: Service Integration Tests
# =============================================================================

class TestServiceConfig(TestCase):
    """Tests for ServiceConfig"""

    def test_default_config(self):
        """Test default configuration values"""
        from .service import ServiceConfig

        config = ServiceConfig()

        self.assertEqual(config.max_steps, 20)
        self.assertEqual(config.max_retries, 3)
        self.assertTrue(config.enable_quick_planning)
        self.assertTrue(config.use_quick_classifier)

    def test_custom_config(self):
        """Test custom configuration"""
        from .service import ServiceConfig

        config = ServiceConfig(
            max_steps=10,
            max_retries=5,
            enable_quick_planning=False
        )

        self.assertEqual(config.max_steps, 10)
        self.assertEqual(config.max_retries, 5)
        self.assertFalse(config.enable_quick_planning)


class TestServiceResult(TestCase):
    """Tests for ServiceResult"""

    def test_default_result(self):
        """Test default result values"""
        from .service import ServiceResult
        from .intake import RouteType

        result = ServiceResult(
            success=True,
            response="Test response",
            route_type=RouteType.DIRECT
        )

        self.assertTrue(result.success)
        self.assertEqual(result.response, "Test response")
        self.assertEqual(result.route_type, RouteType.DIRECT)
        self.assertFalse(result.awaiting_user)
        self.assertEqual(result.affected_entities, {})

    def test_result_with_entities(self):
        """Test result with affected entities"""
        from .service import ServiceResult
        from .intake import RouteType

        result = ServiceResult(
            success=True,
            response="Created tasks",
            route_type=RouteType.EXECUTE,
            affected_entities={'task': [1, 2, 3]}
        )

        self.assertEqual(result.affected_entities, {'task': [1, 2, 3]})


class TestV4RouterResult(TestCase):
    """Tests for V4RouterResult"""

    def test_is_direct_property(self):
        """Test is_direct property"""
        from .router import V4RouterResult
        from .intake import RouteType

        direct_result = V4RouterResult(
            route_type=RouteType.DIRECT,
            response="Direct response",
            success=True
        )

        execute_result = V4RouterResult(
            route_type=RouteType.EXECUTE,
            response="Execute response",
            success=True
        )

        self.assertTrue(direct_result.is_direct)
        self.assertFalse(direct_result.is_agentic)

        self.assertFalse(execute_result.is_direct)
        self.assertTrue(execute_result.is_agentic)

    def test_needs_user_input_property(self):
        """Test needs_user_input property"""
        from .router import V4RouterResult
        from .intake import RouteType

        awaiting_result = V4RouterResult(
            route_type=RouteType.EXECUTE,
            response="Awaiting...",
            success=True,
            awaiting_user=True
        )

        completed_result = V4RouterResult(
            route_type=RouteType.EXECUTE,
            response="Done",
            success=True,
            awaiting_user=False
        )

        self.assertTrue(awaiting_result.needs_user_input)
        self.assertFalse(completed_result.needs_user_input)


class TestChatServiceV4Init(TransactionTestCase):
    """Tests for ChatServiceV4 initialization"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser_service',
            email='testservice@example.com',
            password='testpass123'
        )
        self.conversation = Conversation.objects.create(
            user=self.user,
            title='Test Conversation',
            chat_version='v4'
        )

    def test_service_initialization(self):
        """Test basic service initialization"""
        from .service import ChatServiceV4

        service = ChatServiceV4(self.user, self.conversation)

        self.assertEqual(service.user, self.user)
        self.assertEqual(service.conversation, self.conversation)
        self.assertIsNotNone(service.state)

    def test_service_creates_state(self):
        """Test service creates conversation state"""
        from .service import ChatServiceV4

        service = ChatServiceV4(self.user, self.conversation)

        # Should have created a ConversationState
        self.assertIsNotNone(service.state)
        self.assertEqual(service.state.conversation, self.conversation)

    def test_service_with_custom_config(self):
        """Test service with custom config"""
        from .service import ChatServiceV4, ServiceConfig

        config = ServiceConfig(
            max_steps=5,
            enable_quick_planning=False
        )

        service = ChatServiceV4(self.user, self.conversation, config)

        self.assertEqual(service.config.max_steps, 5)
        self.assertFalse(service.config.enable_quick_planning)

    def test_service_builds_agent_factories(self):
        """Test service builds agent factories"""
        from .service import ChatServiceV4
        from .agents.registry import AgentRegistry

        service = ChatServiceV4(self.user, self.conversation)

        # Should have factories for all registered agents
        registered_agents = AgentRegistry.list_agents()
        for agent_type in registered_agents:
            self.assertIn(agent_type, service._agent_factories)


class TestV4RouterInit(TransactionTestCase):
    """Tests for V4Router initialization"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser_router',
            email='testrouter@example.com',
            password='testpass123'
        )
        self.conversation = Conversation.objects.create(
            user=self.user,
            title='Test Router Conversation',
            chat_version='v4'
        )

    def test_router_initialization(self):
        """Test basic router initialization"""
        from .router import V4Router

        router = V4Router(self.user, self.conversation)

        self.assertEqual(router.user, self.user)
        self.assertEqual(router.conversation, self.conversation)
        self.assertIsNotNone(router.service)

    def test_router_has_pending_execution(self):
        """Test has_pending_execution method"""
        from .router import V4Router

        router = V4Router(self.user, self.conversation)

        # Initially no pending execution
        self.assertFalse(router.has_pending_execution())

    def test_router_cancel_pending(self):
        """Test cancel_pending method"""
        from .router import V4Router

        router = V4Router(self.user, self.conversation)

        # Set a fake active execution
        router.service.state.active_execution_id = 'test-execution-id'
        router.service.state.save()

        self.assertTrue(router.has_pending_execution())

        # Cancel it
        result = router.cancel_pending()
        self.assertTrue(result)
        self.assertFalse(router.has_pending_execution())


class TestConversationModelIntegration(TransactionTestCase):
    """Tests for Conversation model V4 integration"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser_conv',
            email='testconv@example.com',
            password='testpass123'
        )

    def test_enable_v4(self):
        """Test enable_v4 method"""
        conversation = Conversation.objects.create(
            user=self.user,
            title='Test',
            chat_version='v2'
        )

        conversation.enable_v4()

        self.assertEqual(conversation.chat_version, 'v4')
        self.assertTrue(conversation.use_v2)  # Should remain True for V4

    def test_is_v4(self):
        """Test is_v4 method"""
        v4_conversation = Conversation.objects.create(
            user=self.user,
            title='V4 Test',
            chat_version='v4'
        )

        v2_conversation = Conversation.objects.create(
            user=self.user,
            title='V2 Test',
            chat_version='v2'
        )

        self.assertTrue(v4_conversation.is_v4())
        self.assertFalse(v2_conversation.is_v4())

    def test_set_version_v4(self):
        """Test set_version with v4"""
        conversation = Conversation.objects.create(
            user=self.user,
            title='Test',
            chat_version='v2'
        )

        conversation.set_version('v4')

        self.assertEqual(conversation.chat_version, 'v4')
        self.assertTrue(conversation.use_v2)


class TestDirectResponses(TransactionTestCase):
    """Tests for direct response generation"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser_direct',
            email='testdirect@example.com',
            password='testpass123'
        )
        self.conversation = Conversation.objects.create(
            user=self.user,
            title='Direct Test',
            chat_version='v4'
        )

    def _make_context(self):
        """Create a test ConversationContext"""
        from .context import ConversationContext

        return ConversationContext(
            conversation_id=str(self.conversation.id),
            user_id=str(self.user.id),
            summary='',
            topics=[],
            message_count=0,
            mentioned_entities={},
            last_created_entities={},
            last_affected_entities={},
            has_active_execution=False,
            active_execution_id=None,
            last_execution_summary=None,
            recent_messages=[]
        )

    def test_greeting_response(self):
        """Test greeting generates direct response"""
        from .service import ChatServiceV4

        service = ChatServiceV4(self.user, self.conversation)
        context = self._make_context()

        response = service._generate_direct_response("hello", context)

        self.assertIn("Hello", response)

    def test_help_response(self):
        """Test help generates direct response"""
        from .service import ChatServiceV4

        service = ChatServiceV4(self.user, self.conversation)
        context = self._make_context()

        response = service._generate_direct_response("help", context)

        self.assertIn("help", response.lower())
        self.assertIn("tasks", response.lower())

    def test_thanks_response(self):
        """Test thanks generates direct response"""
        from .service import ChatServiceV4

        service = ChatServiceV4(self.user, self.conversation)
        context = self._make_context()

        response = service._generate_direct_response("thanks!", context)

        self.assertIn("welcome", response.lower())
