"""
V4 Agent Tests

Comprehensive tests for each V4 agent action.
Tests verify that agents correctly interact with Django models.
"""

from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from datetime import date, datetime, timedelta
from decimal import Decimal
import json

from accounts.models import User
from notes.models import Note, Tag
from tasks.models import Task
from para.models import Area, Project

from chat.v4.agents.base import AgentContext


class BaseAgentTestCase(TransactionTestCase):
    """
    Base test case with common fixtures for all agent tests.

    Provides:
    - Test user
    - Areas (active and archived)
    - Projects (active and archived)
    - Tasks in various states
    - Notes of different types
    - Tags
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

    def setUp(self):
        """Set up test fixtures for each test"""
        # Create test user
        self.user = User.objects.create_user(
            username='testagent',
            email='testagent@example.com',
            password='testpass123'
        )

        # Create Areas
        self.area_work = Area.objects.create(
            user=self.user,
            name='Work',
            description='Work-related responsibilities',
            is_active=True,
            is_business_area=True
        )
        self.area_personal = Area.objects.create(
            user=self.user,
            name='Personal',
            description='Personal life',
            is_active=True,
            is_business_area=False
        )
        self.area_archived = Area.objects.create(
            user=self.user,
            name='Old Area',
            description='This area is archived',
            is_active=False  # Archived
        )

        # Create Projects
        self.project_active = Project.objects.create(
            user=self.user,
            name='Active Project',
            description='An active project',
            area=self.area_work,
            status='active',
            deadline=date.today() + timedelta(days=30)
        )
        self.project_completed = Project.objects.create(
            user=self.user,
            name='Completed Project',
            description='A completed project',
            area=self.area_work,
            status='completed',
            is_archived=True
        )

        # Create Tasks
        self.task_todo = Task.objects.create(
            user=self.user,
            title='Todo Task',
            description='A task to do',
            status='todo',
            priority='medium',
            container_type='inbox'
        )
        self.task_with_due = Task.objects.create(
            user=self.user,
            title='Due Task',
            description='A task with due date',
            status='todo',
            priority='high',
            due_date=timezone.now() + timedelta(days=1),
            container_type='project',
            container_id=self.project_active.id
        )
        self.task_done = Task.objects.create(
            user=self.user,
            title='Done Task',
            description='A completed task',
            status='done',
            priority='low',
            container_type='inbox'
        )
        self.task_waiting = Task.objects.create(
            user=self.user,
            title='Waiting Task',
            description='A waiting task',
            status='waiting',
            waiting_on='Client response',
            container_type='project',
            container_id=self.project_active.id
        )

        # Create Notes
        self.note_inbox = Note.objects.create(
            user=self.user,
            title='Inbox Note',
            content='Content in inbox',
            note_type='note',
            container_type='inbox'
        )
        self.note_in_project = Note.objects.create(
            user=self.user,
            title='Project Note',
            content='Content in project',
            note_type='note',
            container_type='project',
            container_id=self.project_active.id
        )
        self.note_meeting = Note.objects.create(
            user=self.user,
            title='Meeting Note',
            content='Meeting content',
            note_type='meeting',
            container_type='inbox'
        )

        # Create Tags (Tags don't have user field - they're shared)
        # Use get_or_create since tag names must be unique
        self.tag_work, _ = Tag.objects.get_or_create(
            name='work_test_tag',
            defaults={'tag_type': 'topic'}
        )
        self.tag_important, _ = Tag.objects.get_or_create(
            name='important_test_tag',
            defaults={'tag_type': 'status'}
        )

    def _create_context(self, action: str, params: dict = None, step_id: int = 1) -> AgentContext:
        """
        Helper to create AgentContext for testing.

        Args:
            action: The action to execute
            params: Parameters for the action
            step_id: Step ID in the plan

        Returns:
            AgentContext ready for agent execution
        """
        return AgentContext(
            user_id=self.user.id,
            step_id=step_id,
            action=action,
            params=params or {},
            working_memory={}
        )


# =============================================================================
# Tasks Agent Tests
# =============================================================================

class TestTasksAgent(BaseAgentTestCase):
    """Tests for TasksAgent actions"""

    def setUp(self):
        super().setUp()
        from chat.v4.agents.tasks import TasksAgent
        self.agent = TasksAgent()

    def test_create_basic_task(self):
        """Test creating a task with just title"""
        context = self._create_context('create', {'title': 'New Task'})
        result = self.agent.execute(context)

        self.assertTrue(result.success)
        self.assertIn('task', result.output)
        self.assertEqual(result.output['task']['title'], 'New Task')
        self.assertEqual(result.output['task']['status'], 'todo')
        self.assertEqual(result.output['task']['priority'], 'medium')

    def test_create_task_full_fields(self):
        """Test creating a task with all fields"""
        context = self._create_context('create', {
            'title': 'Full Task',
            'description': 'Task description',
            'priority': 'high',
            'status': 'in_progress',
            'due_date': 'tomorrow',
            'container_type': 'project',
            'container_id': self.project_active.id,
            'recurrence_rule': 'weekly'
        })
        result = self.agent.execute(context)

        self.assertTrue(result.success)
        task = result.output['task']
        self.assertEqual(task['title'], 'Full Task')
        self.assertEqual(task['priority'], 'high')
        self.assertEqual(task['status'], 'in_progress')
        self.assertEqual(task['recurrence_rule'], 'weekly')
        self.assertIsNotNone(task['due_date'])

    def test_create_task_missing_title(self):
        """Test creating task without title fails"""
        context = self._create_context('create', {'description': 'No title'})
        result = self.agent.execute(context)

        self.assertFalse(result.success)
        self.assertIn('Title is required', result.error)

    def test_get_task_exists(self):
        """Test getting an existing task"""
        context = self._create_context('get', {'id': self.task_todo.id})
        result = self.agent.execute(context)

        self.assertTrue(result.success)
        self.assertEqual(result.output['task']['title'], 'Todo Task')

    def test_get_task_not_found(self):
        """Test getting non-existent task"""
        context = self._create_context('get', {'id': 99999})
        result = self.agent.execute(context)

        self.assertFalse(result.success)
        self.assertIn('not found', result.error.lower())

    def test_update_task_fields(self):
        """Test updating task fields"""
        context = self._create_context('update', {
            'id': self.task_todo.id,
            'title': 'Updated Title',
            'priority': 'urgent'
        })
        result = self.agent.execute(context)

        self.assertTrue(result.success)
        self.assertEqual(result.output['task']['title'], 'Updated Title')
        self.assertEqual(result.output['task']['priority'], 'urgent')

    def test_update_task_recurrence_rule(self):
        """Test updating recurrence_rule field specifically"""
        context = self._create_context('update', {
            'id': self.task_todo.id,
            'recurrence_rule': 'daily'
        })
        result = self.agent.execute(context)

        self.assertTrue(result.success)
        self.assertEqual(result.output['task']['recurrence_rule'], 'daily')

    def test_delete_task(self):
        """Test deleting a task"""
        task_id = self.task_done.id
        context = self._create_context('delete', {'id': task_id})
        result = self.agent.execute(context)

        self.assertTrue(result.success)
        self.assertFalse(Task.objects.filter(id=task_id).exists())

    def test_list_tasks_no_filter(self):
        """Test listing tasks without filters"""
        context = self._create_context('list', {})
        result = self.agent.execute(context)

        self.assertTrue(result.success)
        self.assertGreaterEqual(result.output['count'], 3)

    def test_list_tasks_by_status(self):
        """Test listing tasks filtered by status"""
        context = self._create_context('list', {'status': 'todo'})
        result = self.agent.execute(context)

        self.assertTrue(result.success)
        for task in result.output['tasks']:
            self.assertEqual(task['status'], 'todo')

    def test_complete_task(self):
        """Test completing a task"""
        context = self._create_context('complete', {'id': self.task_todo.id})
        result = self.agent.execute(context)

        self.assertTrue(result.success)
        self.assertEqual(result.output['task']['status'], 'done')

    def test_start_task(self):
        """Test starting a task"""
        context = self._create_context('start', {'id': self.task_todo.id})
        result = self.agent.execute(context)

        self.assertTrue(result.success)
        self.assertEqual(result.output['task']['status'], 'in_progress')

    def test_set_waiting(self):
        """Test setting task to waiting"""
        context = self._create_context('set_waiting', {
            'id': self.task_todo.id,
            'waiting_on': 'Manager approval',
            'follow_up_date': 'next week'
        })
        result = self.agent.execute(context)

        self.assertTrue(result.success)
        self.assertEqual(result.output['task']['status'], 'waiting')

    def test_add_subtask(self):
        """Test adding a subtask"""
        context = self._create_context('add_subtask', {
            'parent_id': self.task_todo.id,
            'title': 'Subtask 1'
        })
        result = self.agent.execute(context)

        self.assertTrue(result.success)
        subtask = Task.objects.get(id=result.output['subtask']['id'])
        self.assertEqual(subtask.parent_task_id, self.task_todo.id)

    def test_archive_task(self):
        """Test archiving a task"""
        context = self._create_context('archive', {'id': self.task_done.id})
        result = self.agent.execute(context)

        self.assertTrue(result.success)
        self.task_done.refresh_from_db()
        self.assertTrue(self.task_done.is_archived)


# =============================================================================
# Areas Agent Tests
# =============================================================================

class TestAreasAgent(BaseAgentTestCase):
    """Tests for AreasAgent actions - verifies is_active field usage"""

    def setUp(self):
        super().setUp()
        from chat.v4.agents.areas import AreasAgent
        self.agent = AreasAgent()

    def test_create_area(self):
        """Test creating an area"""
        context = self._create_context('create', {
            'name': 'New Area',
            'description': 'Test area'
        })
        result = self.agent.execute(context)

        self.assertTrue(result.success)
        self.assertEqual(result.output['area']['name'], 'New Area')
        # Verify is_active is True by default
        area = Area.objects.get(id=result.output['area']['id'])
        self.assertTrue(area.is_active)

    def test_list_areas_active_only(self):
        """Test listing only active areas (is_active=True)"""
        context = self._create_context('list', {'is_archived': False})
        result = self.agent.execute(context)

        self.assertTrue(result.success)
        # Should NOT include the archived area
        area_names = [a['name'] for a in result.output['areas']]
        self.assertIn('Work', area_names)
        self.assertIn('Personal', area_names)
        self.assertNotIn('Old Area', area_names)

    def test_list_areas_archived(self):
        """Test listing archived areas (is_active=False)"""
        context = self._create_context('list', {'is_archived': True})
        result = self.agent.execute(context)

        self.assertTrue(result.success)
        # Should only include archived areas
        area_names = [a['name'] for a in result.output['areas']]
        self.assertIn('Old Area', area_names)
        self.assertNotIn('Work', area_names)

    def test_archive_area(self):
        """Test archiving area sets is_active=False"""
        context = self._create_context('archive', {'id': self.area_personal.id})
        result = self.agent.execute(context)

        self.assertTrue(result.success)
        self.area_personal.refresh_from_db()
        self.assertFalse(self.area_personal.is_active)

    def test_unarchive_area(self):
        """Test unarchiving area sets is_active=True"""
        context = self._create_context('unarchive', {'id': self.area_archived.id})
        result = self.agent.execute(context)

        self.assertTrue(result.success)
        self.area_archived.refresh_from_db()
        self.assertTrue(self.area_archived.is_active)

    def test_get_children_active_only(self):
        """Test get_children only returns active children"""
        # Create child areas
        child_active = Area.objects.create(
            user=self.user,
            name='Active Child',
            parent=self.area_work,
            is_active=True
        )
        child_archived = Area.objects.create(
            user=self.user,
            name='Archived Child',
            parent=self.area_work,
            is_active=False
        )

        context = self._create_context('get_children', {'id': self.area_work.id})
        result = self.agent.execute(context)

        self.assertTrue(result.success)
        child_names = [c['name'] for c in result.output['children']]
        self.assertIn('Active Child', child_names)
        self.assertNotIn('Archived Child', child_names)

    def test_search_areas_respects_is_active(self):
        """Test search only returns active areas by default"""
        context = self._create_context('search', {'query': 'Area'})
        result = self.agent.execute(context)

        self.assertTrue(result.success)
        # 'Old Area' is archived, should not be included
        area_names = [a['name'] for a in result.output['areas']]
        self.assertNotIn('Old Area', area_names)


# =============================================================================
# Notes Agent Tests
# =============================================================================

class TestNotesAgent(BaseAgentTestCase):
    """Tests for NotesAgent actions"""

    def setUp(self):
        super().setUp()
        from chat.v4.agents.notes import NotesAgent
        self.agent = NotesAgent()

    def test_create_note_default_type(self):
        """Test creating note uses 'note' type by default (not 'standard')"""
        context = self._create_context('create', {
            'title': 'Test Note',
            'content': 'Test content'
        })
        result = self.agent.execute(context)

        self.assertTrue(result.success)
        self.assertEqual(result.output['note']['note_type'], 'note')

    def test_create_note_all_types(self):
        """Test creating notes of all types"""
        for note_type in ['note', 'checklist', 'meeting', 'resource']:
            context = self._create_context('create', {
                'title': f'{note_type} Note',
                'note_type': note_type
            })
            result = self.agent.execute(context)

            self.assertTrue(result.success, f"Failed for type: {note_type}")
            self.assertEqual(result.output['note']['note_type'], note_type)

    def test_get_note(self):
        """Test getting a note"""
        context = self._create_context('get', {'id': self.note_inbox.id})
        result = self.agent.execute(context)

        self.assertTrue(result.success)
        self.assertEqual(result.output['note']['title'], 'Inbox Note')

    def test_list_notes_by_type(self):
        """Test listing notes filtered by type"""
        context = self._create_context('list', {'note_type': 'meeting'})
        result = self.agent.execute(context)

        self.assertTrue(result.success)
        for note in result.output['notes']:
            self.assertEqual(note['note_type'], 'meeting')


# =============================================================================
# Inbox Agent Tests
# =============================================================================

class TestInboxAgent(BaseAgentTestCase):
    """Tests for InboxAgent actions"""

    def setUp(self):
        super().setUp()
        from chat.v4.agents.inbox import InboxAgent
        self.agent = InboxAgent()

    def test_capture_note(self):
        """Test capturing a note uses correct note_type"""
        context = self._create_context('capture', {
            'content': 'Quick capture content',
            'title': 'Quick Note'
        })
        result = self.agent.execute(context)

        self.assertTrue(result.success)
        note = Note.objects.get(id=result.output['note']['id'])
        self.assertEqual(note.note_type, 'note')  # Not 'standard'
        self.assertEqual(note.container_type, 'inbox')

    def test_list_inbox(self):
        """Test listing inbox items"""
        context = self._create_context('list', {})
        result = self.agent.execute(context)

        self.assertTrue(result.success)
        self.assertIn('notes', result.output)
        self.assertIn('tasks', result.output)
        self.assertIn('total', result.output)

    def test_count_inbox(self):
        """Test counting inbox items"""
        context = self._create_context('count', {})
        result = self.agent.execute(context)

        self.assertTrue(result.success)
        self.assertIn('note_count', result.output)
        self.assertIn('task_count', result.output)
        self.assertIn('total', result.output)

    def test_process_move_to_project(self):
        """Test moving item from inbox to project"""
        context = self._create_context('process', {
            'item_type': 'note',
            'item_id': self.note_inbox.id,
            'container_type': 'project',
            'container_id': self.project_active.id
        })
        result = self.agent.execute(context)

        self.assertTrue(result.success)
        self.note_inbox.refresh_from_db()
        self.assertEqual(self.note_inbox.container_type, 'project')
        self.assertEqual(self.note_inbox.container_id, self.project_active.id)


# =============================================================================
# Organize Agent Tests
# =============================================================================

class TestOrganizeAgent(BaseAgentTestCase):
    """Tests for OrganizeAgent - verifies Area archive uses is_active"""

    def setUp(self):
        super().setUp()
        from chat.v4.agents.organize import OrganizeAgent
        self.agent = OrganizeAgent()

    def test_archive_area_sets_is_active_false(self):
        """Test archiving area through organize agent sets is_active=False"""
        context = self._create_context('archive', {
            'item_type': 'area',
            'item_id': self.area_personal.id
        })
        result = self.agent.execute(context)

        self.assertTrue(result.success)
        self.area_personal.refresh_from_db()
        self.assertFalse(self.area_personal.is_active)

    def test_archive_task_sets_is_archived_true(self):
        """Test archiving task sets is_archived=True"""
        context = self._create_context('archive', {
            'item_type': 'task',
            'item_id': self.task_done.id
        })
        result = self.agent.execute(context)

        self.assertTrue(result.success)
        self.task_done.refresh_from_db()
        self.assertTrue(self.task_done.is_archived)

    def test_move_task_to_project(self):
        """Test moving task to project"""
        context = self._create_context('move', {
            'item_type': 'task',
            'item_id': self.task_todo.id,
            'container_type': 'project',
            'container_id': self.project_active.id
        })
        result = self.agent.execute(context)

        self.assertTrue(result.success)
        self.task_todo.refresh_from_db()
        self.assertEqual(self.task_todo.container_type, 'project')
        self.assertEqual(self.task_todo.container_id, self.project_active.id)


# =============================================================================
# Calendar Agent Tests
# =============================================================================

class TestCalendarAgent(BaseAgentTestCase):
    """Tests for CalendarAgent"""

    def setUp(self):
        super().setUp()
        from chat.v4.agents.calendar import CalendarAgent
        self.agent = CalendarAgent()

    def test_today(self):
        """Test getting today's items"""
        context = self._create_context('today', {})
        result = self.agent.execute(context)

        self.assertTrue(result.success)
        self.assertIn('items', result.output)

    def test_deadlines(self):
        """Test getting upcoming deadlines"""
        context = self._create_context('deadlines', {'days': 60})
        result = self.agent.execute(context)

        self.assertTrue(result.success)
        self.assertIn('deadlines', result.output)


# =============================================================================
# Review Agent Tests
# =============================================================================

class TestReviewAgent(BaseAgentTestCase):
    """Tests for ReviewAgent - verifies Area queries use is_active"""

    def setUp(self):
        super().setUp()
        from chat.v4.agents.review import ReviewAgent
        self.agent = ReviewAgent()

    def test_cleanup_suggestions(self):
        """Test cleanup suggestions uses is_active for Area queries"""
        context = self._create_context('cleanup_suggestions', {})
        result = self.agent.execute(context)

        # Should complete without error (previously would fail on is_archived query)
        self.assertTrue(result.success)
        self.assertIn('suggestions', result.output)
