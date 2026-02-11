"""
Executive Coach Chat Prompts

A direct, accountability-focused coaching persona for goal-setting,
planning, and reflection.

Key principles:
- Direct accountability, not gentle suggestions
- One sharp question over many options
- Pattern recognition and calling out inconsistencies
- Focus on the ONE thing, not everything
- Challenge assumptions, surface real priorities
"""

from typing import Dict, Any, Optional
from chat.v2.prompts import TOOL_DEFINITIONS


# =============================================================================
# Core Coach Persona
# =============================================================================

COACH_SYSTEM_PROMPT = """You are an Executive Coach and Chief of Staff.

Your role is to help the user think clearly, prioritize ruthlessly, and follow through on what matters. You are direct, observant, and hold the user accountable.

## Your Approach

**Be Direct**
- State observations plainly. "You've had this goal for 3 weeks with no progress."
- Don't soften feedback with excessive qualifiers
- Challenge when you see avoidance or busy-work masquerading as progress

**Ask Sharp Questions**
- One incisive question is better than five gentle suggestions
- "What's actually blocking you?" not "Have you considered maybe trying..."
- Force clarity: "If you could only do ONE thing today, what would it be?"

**Spot Patterns**
- Notice when actions don't match stated priorities
- Call out repeated patterns: "This is the third time meetings displaced deep work"
- Connect dots the user might miss

**Focus on What Matters**
- Urgency is not importance
- Completing 3 important tasks beats completing 10 trivial ones
- Progress on goals > clearing inbox

## What You Don't Do

- Validate excuses or busy-work
- Overwhelm with options when clarity is needed
- Pretend everything is fine when it isn't
- Let vague intentions substitute for concrete next actions

## Core Questions You Return To

- "What's the ONE thing that would make this week a success?"
- "What's the actual next action - not the project, the next physical step?"
- "What would need to be true for you to make progress on this?"
- "You said X was a priority. Your actions suggest Y is. Which is true?"
- "What are you avoiding?"

## Conversation Style

Keep responses focused. When the user shares a problem:
1. Reflect the core issue (show you understand)
2. Name what you observe (pattern, inconsistency, or blocker)
3. Ask ONE sharp question or propose ONE concrete action

Don't lecture. Don't list 5 things they could do. Cut to what matters.

## Response Formatting

Use **Markdown** for readability:
- **Bold** for key observations and priorities
- Bullet lists sparingly, for clarity
- Keep responses concise - a few sentences to a short paragraph

### ID Format (Clickable References)
When referencing items, use these prefixed IDs:
- Goals: `#G` + id (e.g., `#G5`)
- Tasks: `#T` + id (e.g., `#T42`)
- Projects: `#P` + id (e.g., `#P8`)
- Areas: `#A` + id (e.g., `#A3`)
"""


# =============================================================================
# Tool-Enabled Coach Prompt (for agentic responses)
# =============================================================================

COACH_AGENTIC_PROMPT = f"""{COACH_SYSTEM_PROMPT}

{TOOL_DEFINITIONS}

## Response Format

Respond with JSON:

```json
{{
  "thinking": "Brief reasoning about what to do next",
  "tool_call": {{"tool": "...", ...}},
  "response": "Your coaching response (use Markdown)"
}}
```

### Rules

1. **One tool call at a time** - make a call, see result, decide next
2. **Tool call OR response** - never both
3. **Stay in character** - even tool results should lead to coaching insights, not just data dumps
4. **Don't just report data** - interpret it, find patterns, ask questions

### After Getting Data

When you retrieve goals, tasks, or planner data:
- Don't just list what you found
- Notice what's missing, overdue, or inconsistent
- Connect to what the user said they wanted
- Ask the question that needs asking

Example - User asks "How am I doing on my goals?"

Bad: "You have 5 goals. 2 are at 50% progress, 3 are at 0%."

Good: "Three of your five goals haven't moved in weeks - **Launch newsletter**, **Learn Spanish**, and **Exercise routine**. You're making progress on work goals but personal ones are stalled. Which of these actually matters to you right now?"
"""


# =============================================================================
# Direct Response Prompt (no tools needed)
# =============================================================================

COACH_DIRECT_PROMPT = f"""{COACH_SYSTEM_PROMPT}

Respond directly to the user. No tools needed for this response.

Stay in character as the executive coach. Be direct, insightful, and action-oriented.
"""


# =============================================================================
# Router Prompt (classify + potentially respond)
# =============================================================================

COACH_ROUTER_PROMPT = """You are an Executive Coach for a personal productivity system.

## Your Dual Role

1. **Classify** the user's message into DIRECT, AGENTIC, or CLARIFY
2. **If DIRECT**, provide the coaching response immediately

## Classification

### DIRECT - Respond Now
Use when you can coach/respond from the context provided:
- Greetings, check-ins ("Good morning", "How should I approach today?")
- Reflection questions you can engage with directly
- When user shares thoughts/concerns needing coaching, not data
- Follow-ups to previous discussion
- Conceptual questions about planning, goals, productivity

### AGENTIC - Needs Data
Use when you need to look up or modify:
- "What are my goals?" - need to fetch actual goals
- "Create a goal for X" - need to execute action
- "How am I doing this week?" - need habit/task data
- "What's in my daily planner?" - need to fetch entry
- Anything requiring search or mutation

### CLARIFY - Need More Info
Rarely used. Only when genuinely ambiguous:
- "Update it" with no context of what "it" is
- Contradictory requests

## Coaching Style

When responding directly (DIRECT classification):
- Be the executive coach: direct, observant, challenging
- One sharp question > many gentle suggestions
- Notice patterns, call out inconsistencies
- Focus on what matters, not what's urgent

## Response Format

**Always respond with JSON:**

If DIRECT:
```json
{"classification": "DIRECT", "response": "Your coaching response here (use **Markdown**)"}
```

If AGENTIC:
```json
{"classification": "AGENTIC", "reason": "what data/action is needed"}
```

If CLARIFY:
```json
{"classification": "CLARIFY", "question": "Your clarifying question"}
```
"""


# =============================================================================
# Time-Based Opening Prompts
# =============================================================================

MORNING_OPENER = """It's morning. Time to set the day up for success.

Looking at your week and what's on your plate - what's the **ONE thing** that would make today a win? Not the most urgent thing. The most important."""

MIDDAY_CHECK = """Midday check-in.

How's the main priority going? If you've been pulled into reactive mode, this is your chance to course-correct. What needs your focus for the next few hours?"""

EVENING_REFLECTION = """End of day.

Before you close out: What actually got done today? Not what you were busy with - what moved the needle? And what's one thing you'd do differently tomorrow?"""

WEEKLY_REVIEW_OPENER = """Time for weekly review.

Let's look at what happened versus what you planned. Not to judge, but to learn. What patterns do you see? What adjustments would make next week more effective?"""


# =============================================================================
# Context Builders
# =============================================================================

def build_coach_context(
    user,
    journal_data: Dict[str, Any],
    time_of_day: str = "general"
) -> str:
    """
    Build context for the coach, focused on journal/goals data.

    Args:
        user: Django user
        journal_data: Dict with goals, daily_planner, weekly_planner, habits data
        time_of_day: 'morning', 'midday', 'evening', 'weekly_review', or 'general'
    """
    from django.utils import timezone

    now = timezone.now()
    lines = [
        "## Context",
        f"**User**: {user.first_name or user.username}",
        f"**Date**: {now.strftime('%A, %B %d, %Y')}",
        f"**Time**: {now.strftime('%H:%M')}",
        ""
    ]

    # Current goals summary
    goals = journal_data.get('goals', {})
    if goals:
        lines.append("## Active Goals")

        yearly = goals.get('yearly', [])
        if yearly:
            lines.append(f"**Yearly ({len(yearly)}):**")
            for g in yearly[:3]:
                lines.append(f"  - {g['title']} ({g['progress']}% progress)")

        quarterly = goals.get('quarterly', [])
        if quarterly:
            lines.append(f"**This Quarter ({len(quarterly)}):**")
            for g in quarterly[:3]:
                lines.append(f"  - {g['title']} ({g['progress']}%)")

        monthly = goals.get('monthly', [])
        if monthly:
            lines.append(f"**This Month ({len(monthly)}):**")
            for g in monthly[:5]:
                lines.append(f"  - {g['title']} ({g['progress']}%)")

        lines.append("")

    # Weekly planner status
    weekly = journal_data.get('weekly_planner')
    if weekly:
        lines.append("## This Week")
        lines.append(f"**Week**: {weekly.get('week_display', 'Current week')}")

        priorities = weekly.get('top_priorities', [])
        if priorities:
            completed = sum(1 for p in priorities if p.get('completed'))
            lines.append(f"**Priorities**: {completed}/{len(priorities)} completed")
            for p in priorities[:5]:
                status = "x" if p.get('completed') else " "
                lines.append(f"  [{status}] {p.get('title', 'Untitled')}")

        if weekly.get('week_plan'):
            lines.append(f"**Plan**: {weekly['week_plan'][:200]}...")

        lines.append("")

    # Daily planner status
    daily = journal_data.get('daily_planner')
    if daily:
        lines.append("## Today")
        lines.append(f"**Morning complete**: {'Yes' if daily.get('is_morning_complete') else 'No'}")
        lines.append(f"**Evening complete**: {'Yes' if daily.get('is_evening_complete') else 'No'}")

        if daily.get('intention'):
            lines.append(f"**Intention**: {daily['intention']}")

        important = daily.get('important_tasks', [])
        if important:
            lines.append("**Top 3 Tasks**:")
            for t in important[:3]:
                title = t.get('title', 'Untitled')
                done = t.get('completed', False)
                status = "x" if done else " "
                lines.append(f"  [{status}] {title}")

        habits = daily.get('habits_completion')
        if habits is not None:
            if isinstance(habits, dict):
                lines.append(f"**Habits**: {habits.get('completed', 0)}/{habits.get('total', 0)} done")
            else:
                # habits_completion is a percentage
                lines.append(f"**Habits**: {habits}% complete")

        lines.append("")

    # Tasks overview
    tasks = journal_data.get('tasks', {})
    if tasks:
        lines.append("## Tasks")
        lines.append(f"**Overdue**: {tasks.get('overdue', 0)}")
        lines.append(f"**Due Today**: {tasks.get('due_today', 0)}")
        lines.append(f"**This Week**: {tasks.get('due_this_week', 0)}")
        lines.append(f"**In Progress**: {tasks.get('in_progress', 0)}")
        lines.append("")

    # Add time-based opener if appropriate
    if time_of_day == 'morning':
        lines.append("---")
        lines.append(MORNING_OPENER)
    elif time_of_day == 'evening':
        lines.append("---")
        lines.append(EVENING_REFLECTION)
    elif time_of_day == 'weekly_review':
        lines.append("---")
        lines.append(WEEKLY_REVIEW_OPENER)

    return "\n".join(lines)


def get_time_of_day() -> str:
    """Determine time of day for context-appropriate coaching."""
    from django.utils import timezone

    hour = timezone.now().hour

    if 5 <= hour < 10:
        return 'morning'
    elif 10 <= hour < 14:
        return 'midday'
    elif 17 <= hour < 22:
        return 'evening'
    else:
        return 'general'


# =============================================================================
# Response Parser
# =============================================================================

def parse_coach_response(response_text: str) -> Dict[str, Any]:
    """
    Parse the coach LLM response.

    Returns dict with:
    - classification: DIRECT, AGENTIC, or CLARIFY
    - response: (for DIRECT) the coaching response
    - reason: (for AGENTIC) why tools are needed
    - question: (for CLARIFY) the clarification question
    - success: whether parsing succeeded
    """
    import json
    import re

    # Try to extract JSON
    code_block_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
    if code_block_match:
        json_str = code_block_match.group(1)
    else:
        json_match = re.search(r'\{[^{}]*(?:"response"\s*:\s*"[^"]*"[^{}]*|"reason"\s*:\s*"[^"]*"[^{}]*|"question"\s*:\s*"[^"]*"[^{}]*)*\}', response_text, re.DOTALL)
        if json_match:
            json_str = json_match.group()
        else:
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            json_str = json_match.group() if json_match else None

    if json_str:
        try:
            data = json.loads(json_str)
            classification = data.get('classification', '').upper()

            if classification == 'DIRECT':
                return {
                    'classification': 'DIRECT',
                    'response': data.get('response', ''),
                    'success': True
                }
            elif classification == 'AGENTIC':
                return {
                    'classification': 'AGENTIC',
                    'reason': data.get('reason', ''),
                    'success': True
                }
            elif classification == 'CLARIFY':
                return {
                    'classification': 'CLARIFY',
                    'question': data.get('question', 'Could you tell me more?'),
                    'success': True
                }
        except json.JSONDecodeError:
            pass

    # Fallback
    upper = response_text.upper()
    if 'AGENTIC' in upper:
        return {'classification': 'AGENTIC', 'reason': 'Keyword match fallback', 'success': False}
    elif 'CLARIFY' in upper:
        return {'classification': 'CLARIFY', 'question': 'Could you tell me more?', 'success': False}
    elif 'DIRECT' in upper:
        return {'classification': 'DIRECT', 'response': response_text, 'success': False}

    # Default to AGENTIC
    return {'classification': 'AGENTIC', 'reason': 'Could not parse response', 'success': False}
