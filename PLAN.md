# Autonome Studio - AI-Native Bioinformatics IDE

## Project Overview

**Project Name**: Autonome Studio  
**Platform**: macOS (Mac Studio)  
**Vision**: A revolutionary AI-Native Bioinformatics IDE that completely abandons traditional "form-filling + SaaS admin dashboard" patterns. Modeled after **Google AI Studio** and **Cursor**.

---

## Design Philosophy

- **IDE Experience First**: No "multiple pages" - only one fullscreen immersive workspace
- **AI Main Stage**: AI Copilot is the absolute core - all file management, bioinformatics tool invocation, and data visualization happen seamlessly within the conversational context
- **Geek Aesthetics**: High-quality Dark Mode design, minimalist, restrained, typography-focused

---

## Technical Stack

### Frontend Requirements

| Component | Technology | Version | Notes |
|-----------|------------|---------|-------|
| Core Framework | Next.js | 16 (App Router) | Latest stable |
| React | React | 19 | Latest stable |
| Styling | Tailwind CSS | v4 | ⚠️ Note: v4 configuration |
| UI Components | Shadcn UI | Latest | With `lucide-react` icons |
| State Management | Zustand | Latest | Minimal global state tree |
| Layout Engine | react-resizable-panels | v4 | ⚠️ CRITICAL: `defaultSize` must be **string percentage** format like `"15%"` |
| Markdown Rendering | react-markdown + remark-gfm + @tailwindcss/typography | Latest | For streaming output formatting |

### Backend Requirements

| Component | Technology | Notes |
|-----------|------------|-------|
| Core Framework | FastAPI | Python |
| LLM Orchestration | LangChain + LangGraph | ReAct multi-agent collaboration system |
| ORM & Database | SQLModel + PostgreSQL |预留 (reserved for future) |
| Task Engine | Celery | For long-running bioinformatics computation tasks |
| Communication | RESTful API + SSE | Server-Sent Events for streaming LLM output |

---

## Core UI Architecture: 3-Panel Layout

### Layout Specifications

- **Container**: `h-screen w-screen`, no global scrollbars
- **Default Ratios**: **15% : 60% : 25%**
- **Library**: `react-resizable-panels` v4

```typescript
// ⚠️ CRITICAL: react-resizable-panels v4 requires STRING percentages
<PanelGroup direction="horizontal">
  <Panel defaultSize="15%" minSize={10} maxSize={20}>
    {/* Left Panel: Navigation & History */}
  </Panel>
  <Panel defaultSize="60%" minSize={40}>
    {/* Center Panel: AI Main Stage */}
  </Panel>
  <Panel defaultSize="25%" minSize={15} maxSize={35}>
    {/* Right Panel: Context & Assets */}
  </Panel>
</PanelGroup>
```

### Panel 1: Left Panel (15%) - Navigation & History

**Components**:
- **Header**: Logo + System name
- **Primary Navigation**:
  - Control Panel (system dashboard)
  - Project Center
  - Task Center
- **Session List**: User's historical conversation sessions (supports create/collapse)
- **Footer**: Docs Center, Settings, Account
- **Behavior**: Collapsible

### Panel 2: Center Panel (60%) - AI Main Stage

**Components**:
- **Message Stream**: Top-to-bottom streaming layout
- **Message Container**: `max-w-4xl mx-auto` for optimal reading
- **Markdown Support**: Full markdown + code block syntax highlighting
- **Input Dock**: Floating multi-line text input at bottom
  - Supports `Ctrl+Enter` to send
  - Minimal micro-interactions

### Panel 3: Right Panel (25%) - Context & Assets

**Upper Section**:
- **Data Center**: User files (tree/list view), drag-drop upload, folder management
- **Tool Center**: Registered bioinformatics workflows/tools, searchable, collapsible

**Lower Section**:
- **Dynamic Toolbox**: Context-sensitive parameter panel
  - Renders JSON Schema-based forms based on selected tool
  - Execute Task button

---

## Core Functional Modules

### Module A: AI Copilot Hub (Center Panel)

**Role**: System's灵魂 (soul) and orchestration hub. Not just a chat window - it's the Agentic Workflow execution engine.

**Features**:
- **Streaming Output**: SSE-based typewriter effect
- **Intent Parsing**: Real-time analysis of natural language → API calls to other modules
- **Context Aware**: Can "see" mounted files and tools

### Module B: Global Management Matrix (Left Panel)

**Components**:

1. **Control Panel** (控制面板)
   - User resource usage (CPU/Memory/Storage quotas)
   - Active tasks overview
   - System health status

2. **Project Center** (项目中心)
   - Workspace-level data isolation
   - Each project has independent: Sessions, File tree, Task queue
   - Context switches instantly across all panels

3. **Task Center** (任务中心)
   - Celery + Nextflow integration
   - Historical and running task lists
   - Streaming logs, resource consumption, output directory links

4. **Infrastructure** (基建中心)
   - Docs Center: Bioinformatics best practices, platform manual
   - Settings: Theme, Language, LLM API keys, compute node config
   - Account: Profile, team permissions, billing

### Module C: Assets & Execution Engine (Right Panel)

**Components**:

1. **Data Center** (Upper)
   - File tree for current project (Fastq, BAM, CSV, etc.)
   - Drag-drop upload
   - Context mounting: `[+]` button to feed files to AI

2. **Tool Center** (Upper)
   - Tool registry (RNA-Seq QC, Variant Calling, Single-cell, etc.)
   - AI-assisted tool building
   - Search + collapse

3. **Dynamic Toolbox** (Lower)
   - **Core Innovation**: Dynamic parameter panel
   - Renders JSON Schema forms based on selected tool
   - Execute Task button pushes to Task Center

---

## Interaction Patterns

### Overlay System (Slide-out Overlays)

Use **Framer Motion** + **Zustand** for smooth transitions:

```typescript
// Zustand store
interface AppState {
  isProjectCenterOpen: boolean;
  isTaskCenterOpen: boolean;
  // ...
}

// Component pattern
{isProjectCenterOpen && (
  <motion.div 
    className="absolute inset-0 z-50"
    initial={{ x: '100%' }}
    animate={{ x: 0 }}
    exit={{ x: '100%' }}
  >
    <ProjectCenterOverlay />
  </motion.div>
)}
```

### Scenario: RNA-Seq QC Workflow

1. **Initialize**: User clicks Left Panel → Project Center → Slide-out fullscreen overlay → Create/Select project → Overlay retracts → Context switches

2. **Prepare Data**: Right Panel → Data Center → Drag-drop 4 `.fastq.gz` files → Check `[+]` to mount to AI context

3. **Intent**: Center Panel → Input: "QC selected data with strictest parameters"

4. **Smart Scheduling**: 
   - AI parses tool: "RNA-Seq QC Pipeline"
   - AI auto-selects tool in Tool Center
   - AI auto-fills Dynamic Toolbox parameters (e.g., Quality Threshold: 20 → 30)

5. **Confirm**: User reviews Dynamic Toolbox → Click "Execute Task"

6. **Monitor**: 
   - Task pushed to compute cluster
   - Center Panel: "Task submitted! Monitor in Task Center"
   - Left Panel → Task Center → Slide-out fullscreen → Real-time logs (streaming), resource charts

---

## Development Guidelines

### Phase 1: Project Setup

1. Initialize Next.js 16 project with App Router
2. Install dependencies:
   ```bash
   npm install next@16 react@19 tailwindcss@4 @tailwindcss/vite
   npm install shadcn-ui lucide-react
   npm install zustand
   npm install react-resizable-panels@4
   npm install react-markdown remark-gfm @tailwindcss/typography
   npm install framer-motion
   ```

3. Configure Tailwind CSS v4 with dark mode

### Phase 2: Core Layout

1. Implement 3-panel layout with react-resizable-panels v4
2. Create Zustand store for global state
3. Implement slide-out overlay system with Framer Motion
4. Set up dark theme foundation

### Phase 3: Module Implementation

Follow the order:
1. AI Copilot Hub (Center Panel) - Streaming + Markdown
2. Global Management (Left Panel) - Navigation, Projects, Tasks
3. Assets & Tools (Right Panel) - Data tree, Tool registry, Dynamic forms

### Phase 4: Backend Integration

1. FastAPI backend setup
2. LangChain + LangGraph for agent orchestration
3. SSE streaming implementation
4. Celery task queue integration

---

## Critical Implementation Notes

### ⚠️ react-resizable-panels v4 Breaking Change

```typescript
// ❌ WRONG - v3 format (will break)
<Panel defaultSize={15} />

// ✅ CORRECT - v4 format (string percentage)
<Panel defaultSize="15%" />
```

### Animation Library

Use **Framer Motion** for all transitions:
- Panel slide-outs
- Panel collapses
- Modal overlays
- Micro-interactions

### State Management

Use **Zustand** for:
- Current project context
- Overlay visibility states
- Selected tool state
- AI conversation history
- User preferences

### Code Style

- TypeScript strict mode
- No `any` type suppressions
- Component-first architecture
- Dark mode first (design in dark, adapt light if needed)

---

## User Stories (Epic Summary)

| Epic | Description |
|------|-------------|
| Epic 1 | Immersive conversation & code generation |
| Epic 2 | Seamless data asset operations |
| Epic 3 | AI-driven task execution |
| Epic 4 | AI-as-a-Developer (custom tool building) |
| Epic 5 | Result visualization & deep interpretation |
| Epic 6 | Collaboration & resource monitoring |

---

## Environment

- **Platform**: macOS (Mac Studio)
- **Development**: Local development environment
- **Future**: Deployment considerations for production

---

*Generated from Autonome Studio Master Blueprint*
*Last Updated: 2026-03-02*
