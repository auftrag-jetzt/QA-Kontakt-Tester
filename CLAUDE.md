# CLAUDE.md — Instructions for AI Assistants

This file guides AI assistants on how to work on this project.

---

## 📖 START HERE

When you start working on this project:

1. **Read AI_CONTEXT.md first** — System design, architecture, and how everything works
2. **Check PROGRESS.md** — See what's done and what's pending
3. **Review recent git commits** — `git log --oneline -10` to see recent work
4. **Ask clarifying questions** — Don't assume; ask the user if unclear

---

## 🎯 YOUR ROLE

You are helping with:
- Code implementation and debugging
- Documentation updates
- Deployment guidance
- Testing and validation
- Architecture decisions (with user approval)

**You are NOT:**
- Making autonomous production deployments
- Deleting files without explicit approval
- Committing code without user consent
- Making major architecture changes without discussion

---

## 🔍 UNDERSTANDING THE SYSTEM

### Key Files to Know

| File | Purpose | For AI |
|------|---------|--------|
| **visual_qa.py** | Core QA pipeline | Main logic; read carefully |
| **webhook-server/app.py** | Flask webhook server | Entry point for requests |
| **form_automation.py** | Contact form testing | Secondary logic |
| **gemini_analyzer.py** | Visual analysis | Gemini API integration |
| **airtable_verifier.py** | Airtable checks | API interaction patterns |
| **AI_CONTEXT.md** | System design | Read this first! |
| **PROGRESS.md** | Current status | Your navigation guide |

### The Flow

```
User clicks Airtable button
  ↓
Airtable automation sends webhook
  ↓
webhook-server/app.py receives POST /run-qa
  ↓
Calls visual_qa.run_domain(domain, record_id)
  ↓
visual_qa.py orchestrates:
  1. Screenshot (Playwright)
  2. Gemini analysis
  3. Form submission
  4. Airtable checks
  ↓
Result written back to Airtable
  ↓
User sees passed/failed + error details
```

---

## ✅ BEFORE MAKING CHANGES

### Checklist Before Any Code Change

- [ ] Read AI_CONTEXT.md (system design)
- [ ] Read PROGRESS.md (current status)
- [ ] Check git log (recent changes)
- [ ] Understand what the user is asking for
- [ ] Ask clarifying questions if unclear
- [ ] Get user approval for approach before coding
- [ ] Update PROGRESS.md after completing work

### Never Do These Without Explicit User Approval

- ❌ Delete files
- ❌ Rename files (except documentation consolidation)
- ❌ Deploy to production
- ❌ Change API/webhook contract
- ❌ Remove features
- ❌ Force push to git
- ❌ Commit code you wrote without asking

---

## 📝 DOCUMENTATION RESPONSIBILITIES

### When to Update Documentation

**Update AI_CONTEXT.md when:**
- System architecture changes
- New major components are added
- API contracts change
- Two-table Airtable setup changes

**Update PROGRESS.md when:**
- User completes a task (mark as completed)
- You start new work (mark as in_progress)
- Blockers appear (add to "Known Issues")
- Next steps change

**Update README.md when:**
- How to use the system changes
- New features are added
- Setup instructions change

**Create new .md files when:**
- Documenting major features
- Providing deployment guides
- Explaining non-obvious architecture decisions

### Files to Never Delete

✅ Must keep:
- AI_CONTEXT.md
- README.md
- PROGRESS.md
- PREREQUISITES.md
- COOLIFY_DEPLOYMENT.md
- CLAUDE.md (this file)

### Consolidation Strategy

When documentation gets messy:
1. Identify overlap
2. Ask user which files to consolidate
3. Get explicit approval to delete
4. Merge content carefully
5. Update all cross-references

---

## 🚀 COMMON TASKS & APPROACH

### Task: Fix a Bug

1. Read AI_CONTEXT.md to understand system
2. Reproduce the bug locally if possible
3. Find the root cause (git log helps)
4. Write a fix
5. Test if possible
6. Update PROGRESS.md
7. Commit with clear message

### Task: Add a Feature

1. Discuss approach with user first
2. Get approval before coding
3. Read relevant code sections
4. Implement incrementally
5. Test thoroughly
6. Update documentation
7. Update PROGRESS.md
8. Commit with clear message

### Task: Deploy to Production

1. Never do this without explicit user request
2. Verify all code is committed and pushed
3. Verify PROGRESS.md is up-to-date
4. Follow COOLIFY_DEPLOYMENT.md
5. Test in staging first if possible
6. Get user confirmation before final step
7. Update PROGRESS.md with deployment details

### Task: Update Documentation

1. Identify which files need updating
2. Read current content carefully
3. Make changes
4. Check for cross-references
5. Commit with clear message explaining why

---

## 🔧 DEVELOPMENT PRACTICES

### Code Style

- Follow Python PEP 8
- Use descriptive variable names
- Add comments only for WHY, not WHAT
- Keep functions under 50 lines when possible
- Use type hints where helpful

### Testing

- Test manually when possible
- Check logs for errors
- Verify Airtable integration works
- Test error cases, not just happy path
- Document any testing done in commit message

### Git Commits

Format:
```
One-line summary of what changed

Longer explanation if needed:
- What was broken/missing
- How was it fixed
- Any important details

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>
```

### Error Handling

- Catch specific exceptions, not broad ones
- Log errors clearly
- Write errors back to Airtable when relevant
- Test what happens when APIs fail
- Don't swallow exceptions silently

---

## 🤔 DECISION POINTS

### When to Ask the User

Ask before deciding:
- Architectural changes (e.g., use async vs sync)
- Major refactoring
- Deleting code or features
- Significant performance optimizations
- Changing API contracts
- Adding new dependencies
- Consolidating documentation

### When You Can Decide

You can decide:
- Variable naming
- Comment content
- Test data values
- Non-breaking code restructuring
- Documentation wording
- Bug fixes (if obvious)

---

## 📊 STATUS TRACKING

### How to Update PROGRESS.md

**When starting work:**
```markdown
- [ ] Your task here
```

**When in progress:**
```markdown
- [ ] Your task here (IN_PROGRESS)
```

**When complete:**
```markdown
- [x] Your task here
```

**For blockers:**
Add to "Known Issues" section and explain what's blocking.

---

## 🚨 CRITICAL THINGS TO KNOW

### Never Hardcode Secrets
- API keys go in environment variables
- Use os.environ.get() with defaults
- .env files never committed to git

### Airtable Has Two Tables
- Table A: "Leads Partner" — test lead submissions
- Table B: "EMD Webseiten" — trigger + results
- They're in different bases with different API keys
- Don't mix them up!

### The Trigger is Field-Based
- When "Kontakt status" = "to be tested", webhook fires
- Automation sets it to "testing" to prevent duplicates
- Then pipeline runs and sets final result: "passed"/"failed"
- Error details go to "Kontakt error" field

### Playwright is Async
- Lots of `await` and `async def`
- run_domain() is synchronous but calls async code internally
- Screenshot, form submission, Airtable checks all async

### Error Handling Matters
- Errors are written back to Airtable
- Users see them in "Kontakt error" field
- Must capture and include details

---

## 🎓 LEARNING RESOURCES

If unfamiliar with:

| Technology | Resource |
|------------|----------|
| **Playwright** | https://playwright.dev/ |
| **Flask** | https://flask.palletsprojects.com/ |
| **Airtable API** | https://airtable.com/api |
| **Google Gemini** | https://ai.google.dev/docs |
| **Async Python** | https://docs.python.org/3/library/asyncio.html |

---

## ✋ APPROVAL WORKFLOW

For non-trivial changes:

1. **Propose** — "I think we should X because Y"
2. **Get feedback** — User approves or suggests changes
3. **Implement** — Write code based on approval
4. **Report** — "Done. Changed X files, here's what it does"
5. **Document** — Update PROGRESS.md and relevant docs
6. **Commit** — Push with clear message

---

## 🆘 WHEN STUCK

If you encounter issues:

1. **Check AI_CONTEXT.md** — Does the system design explain this?
2. **Check git log** — How was this handled before?
3. **Check README/docs** — Is there existing documentation?
4. **Ask the user** — "I'm unclear about X, can you clarify?"
5. **Propose a solution** — "Option A: X, Option B: Y. What's best?"

**Never:**
- Guess and hope for the best
- Delete things to make errors go away
- Make major changes without asking

---

## 📋 QUICK REFERENCE

**Your checklist for any session:**

- [ ] Read PROGRESS.md first
- [ ] Check `git log --oneline -10`
- [ ] Understand what user is asking
- [ ] Ask clarifying questions if needed
- [ ] Get approval for approach before coding
- [ ] Make changes
- [ ] Test if possible
- [ ] Update PROGRESS.md
- [ ] Commit with clear message
- [ ] Report to user what was done

---

## 🎯 GOAL

Help the user build and deploy a rock-solid QA automation system that:
✅ Catches website issues automatically  
✅ Integrates seamlessly with Airtable  
✅ Runs reliably in production  
✅ Provides clear error messages to users  
✅ Is easy to maintain and extend  

Go forth and build great things! 🚀
