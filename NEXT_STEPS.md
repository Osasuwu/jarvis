# Jarvis AI Agent — NEXT STEPS (Action Plan)

## 🎯 What You Need to Do Now

### Option A: Start Small (1-2 weeks)
```bash
# 1. Read the analysis
cat ARCHITECTURE_REVIEW.md          # 30 min
cat IMPLEMENTATION_GUIDE.md         # 20 min

# 2. Pick ONE issue to fix
git checkout -b feature/tool-discovery

# 3. Implement from IMPLEMENTATION_GUIDE.md
# (Tool Discovery System section)

# 4. Test thoroughly
pytest tests/unit/test_tool_discovery.py -v --cov

# 5. Create PR for review
git push origin feature/tool-discovery
```

### Option B: Plan Full Q1 (Strategic)
```bash
# 1. Schedule team meeting (1 hour)
# 2. Review architecture with team
# 3. Create issue tickets from roadmap
# 4. Assign to sprints
# 5. Track progress bi-weekly
```

---

## 📊 Decision Matrix: What to Fix First?

```
┌──────────────────────────────┬─────────┬────────────┐
│ Issue                        │ Effort  │ Priority   │
├──────────────────────────────┼─────────┼────────────┤
│ 1. Tool Auto-Discovery       │ 2-3d    │ 🔴 BLOCK   │
│ 2. Error Handling            │ 2-3d    │ 🔴 CRITICAL│
│ 3. Structured Logging        │ 1-2d    │ 🟠 HIGH    │
│ 4. Smart Memory              │ 2-3d    │ 🟠 MEDIUM  │
│ 5. Caching                   │ 2d      │ 🟠 MEDIUM  │
└──────────────────────────────┴─────────┴────────────┘

RECOMMENDED ORDER:
Week 1-2:  #1 + #2 (Foundation)
Week 3-4:  #3 + #4 (Operations)
Week 5-6:  #5 + Testing

SINGLE ISSUE (if time limited):
→ FIX #1 FIRST (Tool Discovery)
  It blocks other work
```

---

## 🚀 Quick Start: Tool Discovery Implementation

### Pre-Implementation Checklist
```bash
# 1. Create feature branch
git checkout -b feature/tool-discovery
git branch -u origin/main

# 2. Create stub files
touch src/jarvis/tools/discovery.py
touch src/jarvis/tools/loader.py
touch tests/unit/test_tool_discovery.py

# 3. Update dependencies in pyproject.toml
# (Already has PyYAML for tools.yaml)

# 4. Verify tests run
pytest tests/ -x -v
```

### Implementation Steps (Day by day)
```
DAY 1:
└─ Copy code from IMPLEMENTATION_GUIDE.md
   ├─ src/jarvis/tools/discovery.py (100+ lines)
   ├─ src/jarvis/tools/loader.py (30 lines)
   └─ Create configs/tools.yaml

DAY 2:
└─ Write tests for discovery
   ├─ test_discover_builtin_tools
   ├─ test_discover_from_directory
   ├─ test_discover_from_config
   └─ test_deduplication

DAY 3:
└─ Update main.py to use discovery
   ├─ Replace hardcoded registration
   ├─ Test with CLI
   └─ Verify all tools still load

DAY 4 (Optional):
└─ Polish & code review
   ├─ Type checking (mypy)
   ├─ Linting (ruff, black)
   ├─ Pre-commit checks
```

### Test Before Committing
```bash
# Run all checks
black src/jarvis/tools/
ruff check src/jarvis/tools/ --fix
mypy src/jarvis/tools/

# Run tests
pytest tests/unit/test_tool_discovery.py -v --cov

# Verify existing functionality
pytest tests/ -k "not discovery" --tb=short

# Check coverage
pytest --cov=src/jarvis --cov-report=html
open htmlcov/index.html
```

---

## 📋 Implementation Checklist

### Phase 7 Sprint 1 (Week 1-2)

```
TOOL DISCOVERY
[  ] Create src/jarvis/tools/discovery.py
[  ] Create src/jarvis/tools/loader.py
[  ] Create configs/tools.yaml.example
[  ] Update src/jarvis/main.py to use discovery
[  ] Write 15-20 unit tests
[  ] Update __init__.py imports
[  ] Test with all built-in tools
[  ] Create user documentation

ERROR HANDLING
[  ] Create src/jarvis/core/exceptions.py
[  ] Create src/jarvis/core/resilience.py
[  ] Update src/jarvis/core/orchestrator.py
[  ] Add retry logic for LLM
[  ] Add timeout management
[  ] Add error-specific handling
[  ] Write 15-20 unit tests
[  ] Create error recovery tests
[  ] Document error types

QUALITY CHECKS
[  ] All tests pass (>90% coverage)
[  ] No type errors (mypy)
[  ] Code formatted (black)
[  ] Linter passes (ruff)
[  ] Pre-commit checks pass
[  ] Documentation updated
[  ] Changelog updated
```

---

## 🏗️ File Structure After Implementation

```
src/jarvis/
├── __init__.py
├── main.py                          (UPDATED: use discovery)
├── config.py
├── core/
│   ├── orchestrator.py              (UPDATED: error handling)
│   ├── planner.py
│   ├── executor.py
│   ├── resilience.py                (NEW)
│   ├── exceptions.py                (NEW)
│   └── cache.py                     (FUTURE)
├── tools/
│   ├── __init__.py                  (UPDATED: exports)
│   ├── base.py
│   ├── registry.py
│   ├── discovery.py                 (NEW)
│   ├── loader.py                    (NEW)
│   ├── builtin/
│   │   ├── __init__.py
│   │   ├── echo.py
│   │   └── ...
│   └── custom/                      (NEW: user tools)
│       └── __init__.py
├── llm/
├── memory/
├── gap_analyzer/
├── safety/
├── ui/
├── observability/                   (NEW: future)
│   ├── logging.py                   (FUTURE)
│   ├── metrics.py                   (FUTURE)
│   └── tracing.py                   (FUTURE)
└── cli/

configs/
├── tools.yaml                       (NEW)
└── tools.yaml.example               (NEW: reference)

docs/
├── ARCHITECTURE_REVIEW.md           (NEW: analysis)
├── IMPLEMENTATION_GUIDE.md          (NEW: code)
├── ANALYSIS_SUMMARY.md              (NEW: quick ref)
├── ISSUES_VISUAL_SUMMARY.md         (NEW: visual)
├── TOOL_DEVELOPMENT.md              (FUTURE)
└── ...existing files...

tests/
├── unit/
│   ├── test_tool_discovery.py       (NEW)
│   ├── test_resilience.py           (NEW)
│   └── ...existing tests...
├── integration/                     (FUTURE)
└── e2e/                            (FUTURE)
```

---

## 🧪 Testing Strategy

### Unit Tests (Immediate)
```python
# tests/unit/test_tool_discovery.py

def test_discover_builtin_tools():
    discovery = ToolDiscovery()
    tools = discovery.discover_builtin_tools()
    assert len(tools) > 0
    assert "echo" in [t.name for t in tools]

def test_discover_from_directory():
    discovery = ToolDiscovery()
    tools = discovery.discover_from_directory("./custom_tools")
    # Check if tools loaded or empty if dir doesn't exist
    assert isinstance(tools, list)

def test_discover_all():
    discovery = ToolDiscovery()
    tools = discovery.discover_all()
    # Should have builtin tools at minimum
    assert len(tools) > 0

def test_no_duplicate_tools():
    discovery = ToolDiscovery()
    tools = discovery.discover_all()
    names = [t.name for t in tools]
    assert len(names) == len(set(names))

# + 15-20 more tests...
```

### Integration Tests (Phase 7 Week 2)
```python
# tests/integration/test_discovery_integration.py

@pytest.mark.asyncio
async def test_orchestrator_with_discovered_tools():
    discovery = ToolDiscovery()
    tools = discovery.discover_all()
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool)
    
    orchestrator = Orchestrator(llm, registry)
    result = await orchestrator.run("List files in current directory")
    assert result  # Should complete without errors
```

---

## 📚 Documentation to Create

### For Developers
```markdown
docs/TOOL_DEVELOPMENT.md
├── 1. Getting Started
├─── Creating your first tool
├─── Tool template
├─── Testing your tool
├─ 2. Advanced Patterns
├─── Async execution
├─── Error handling
├─── Caching results
├─ 3. Safety & Security
├─── Risk levels
├─── Confirming actions
├─── Whitelisting
└─ 4. Examples
    ├─── Simple tool (50 lines)
    ├─── Medium tool (150 lines)
    └─── Complex tool (300 lines)
```

### For Users
```markdown
docs/CONFIGURATION.md
├── 1. Tool Registration
├─── Built-in tools
├─── Custom tools
├─── Configuration file
├─ 2. Environment Variables
├─── Tool-specific config
├─── Feature flags
└─ 3. Troubleshooting
    ├─── Tool not loading
    ├─── Tool timeout
    └─── Error handling
```

---

## 🔍 Code Review Checklist

### For PR Reviewers
```markdown
## Tool Discovery PR Review

### Structure
- [ ] discovery.py implements all required methods
- [ ] loader.py handles file loading correctly
- [ ] tools.yaml is valid YAML
- [ ] main.py correctly uses discovery

### Functionality
- [ ] discover_builtin_tools() works
- [ ] discover_from_directory() works
- [ ] discover_from_config() works
- [ ] discover_all() combines all sources
- [ ] Deduplication works
- [ ] Error handling is graceful

### Quality
- [ ] All tests pass (>90% coverage)
- [ ] No type errors (mypy clean)
- [ ] Code formatted (black)
- [ ] Linter passes (ruff)
- [ ] No warnings
- [ ] Docstrings complete

### Documentation
- [ ] Docstrings for all public methods
- [ ] README updated
- [ ] CHANGELOG updated
- [ ] Comments explain complex logic
- [ ] Examples provided

### Performance
- [ ] No N+1 issues
- [ ] Loading time reasonable (<1s)
- [ ] Memory usage acceptable
- [ ] No memory leaks in tests
```

---

## 🚨 Common Pitfalls to Avoid

### ❌ Don't
```python
# ❌ DON'T: Loose error handling
try:
    module = importlib.import_module(source)
except:  # Too broad!
    pass

# ❌ DON'T: Global state
tools_cache = {}  # Global!

# ❌ DON'T: Hardcoded paths
config_file = "/home/user/tools.yaml"  # Hardcoded!

# ❌ DON'T: No validation
tool = load_tool_from_config(config)  # What if config is invalid?
```

### ✅ DO
```python
# ✅ DO: Specific error handling
try:
    module = importlib.import_module(source)
except ImportError as e:
    logger.error(f"Failed to import {source}: {e}")
    return None

# ✅ DO: Encapsulate state
class ToolDiscovery:
    def __init__(self):
        self._discovered_tools = {}  # Instance variable

# ✅ DO: Relative paths
config_file = workspace_root / "configs" / "tools.yaml"

# ✅ DO: Validate everything
def _load_tool_from_spec(self, spec: dict) -> Tool | None:
    if not spec.get("name"):
        logger.error("Tool spec must have name")
        return None
```

---

## 📞 Getting Help

### Questions?
- Review IMPLEMENTATION_GUIDE.md for code examples
- Check ARCHITECTURE_REVIEW.md for design decisions
- Look at existing tool implementations in src/jarvis/tools/builtin/

### Issues?
- Create GitHub issue with:
  - What you tried
  - Error message
  - Relevant code snippet
  - Expected vs actual behavior

### Code Review?
- Create PR with descriptive message
- Reference related issues
- Include tests
- Add documentation

---

## ✨ Success Criteria

### When is Tool Discovery Complete?
```
✅ DEFINITION OF DONE:

Code:
[  ] discovery.py fully implemented
[  ] loader.py fully implemented
[  ] main.py updated
[  ] All hardcoded registrations removed

Tests:
[  ] 15+ unit tests
[  ] >90% coverage
[  ] All tests pass

Quality:
[  ] mypy: 0 errors
[  ] ruff: 0 warnings
[  ] black: formatted
[  ] pre-commit: passes

Documentation:
[  ] Docstrings complete
[  ] README section added
[  ] Example tools.yaml provided
[  ] CHANGELOG updated

Integration:
[  ] Works with all 7 built-in tools
[  ] Custom tools load correctly
[  ] Config file loading works
[  ] No performance regression

User Experience:
[  ] CLI still works normally
[  ] Error messages are clear
[  ] Documentation is helpful
```

---

## 🎉 Next Steps Summary

```
TODAY:
└─ Read ARCHITECTURE_REVIEW.md (30 min)

THIS WEEK:
└─ Review with your team
└─ Create GitHub issues
└─ Assign to sprints

WEEK 1:
└─ Start Tool Discovery implementation
└─ Set up feature branch
└─ Get code review feedback

WEEK 2:
└─ Finish Tool Discovery
└─ Merge to main
└─ Start Error Handling

WEEK 3-4:
└─ Error Handling complete
└─ Structured Logging
└─ Memory management

By END OF Q1:
└─ 90%+ coverage
└─ Production-ready error handling
└─ Full observability
└─ Ready for external developers
```

---

## 📌 Key Files Reference

```
Core Analysis Documents (Read First):
├─ ARCHITECTURE_REVIEW.md          (28 KB) 📊
├─ IMPLEMENTATION_GUIDE.md         (35 KB) 💻
├─ ANALYSIS_SUMMARY.md             (15 KB) 📋
└─ ISSUES_VISUAL_SUMMARY.md        (20 KB) 📈

Implementation Files (Copy/Reference):
├─ IMPLEMENTATION_GUIDE.md:
│  ├─ Tool Discovery System (copy discovery.py)
│  ├─ Error Handling (copy resilience.py)
│  ├─ Structured Logging (copy logging.py)
│  ├─ Smart Memory (copy smart_memory.py)
│  └─ Caching (copy cache.py)
└─ TOOL_DEVELOPMENT.md (create from scratch)
```

---

**Ready to Start? →** Begin with ARCHITECTURE_REVIEW.md  
**Have Questions? →** Check IMPLEMENTATION_GUIDE.md  
**Need Quick Answers? →** See ANALYSIS_SUMMARY.md  

---

**Generated:** January 16, 2026  
**Prepared for:** Implementation Phase  
**Estimated Time:** 8 weeks for full improvements  

Good luck! 🚀

