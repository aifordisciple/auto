# AUTONOME-STUDIO - Next.js 16 IDE Frontend

## OVERVIEW

AI-Native Bioinformatics IDE frontend. 3-panel layout with Zustand state, Framer Motion animations, SSE streaming chat.

## STRUCTURE

```
src/
├── app/              # Next.js App Router pages
│   ├── page.tsx      # Main IDE workspace
│   ├── login/        # Auth page
│   ├── admin/        # Admin dashboard
│   └── share/[token] # Shared project access
├── components/
│   ├── chat/         # ChatStage, message components
│   ├── layout/       # Sidebar, panels
│   └── overlays/     # Modal overlays (ProjectCenter, TaskCenter, etc.)
├── store/            # Zustand stores (useChatStore, useWorkspaceStore, etc.)
└── lib/
    ├── api.ts        # Backend API client
    └── utils.ts      # Utilities (cn, etc.)
```

## WHERE TO LOOK

| Task | Location |
|------|----------|
| Add page | `src/app/*/page.tsx` |
| Add store | `src/store/useXxxStore.ts` |
| API calls | `src/lib/api.ts` |
| Chat UI | `src/components/chat/` |
| Overlay modal | `src/components/overlays/` |
| Sidebar | `src/components/layout/Sidebar.tsx` |

## CONVENTIONS

- **Path alias**: Import as `@/lib/api`, `@/store/useChatStore`
- **State**: Zustand stores in `src/store/`, persist selectively
- **Styling**: Tailwind CSS v4 + shadcn/ui patterns (`cn()`, `class-variance-authority`)
- **Dark mode**: Default — `<html lang="en" className="dark">`

## ANTI-PATTERNS (CRITICAL)

```typescript
// ❌ WRONG - react-resizable-panels v4
<Panel defaultSize={15} />

// ✅ CORRECT - string percentage
<Panel defaultSize="15%" />
```

- **NEVER** use `any` type (11 violations across 9 files)
- **NEVER** use Context API for global state — use Zustand
- **NEVER** use numeric Panel sizes (5 violations in page.tsx)
- **NEVER** use `console.log()` (7 instances in login/page.tsx)
## 3-PANEL LAYOUT

```
┌─────────┬────────────────────────┬───────────┐
│  15%    │         60%            │   25%     │
│ Sidebar │    ChatStage (AI)      │  Assets   │
│ Nav     │    SSE streaming       │  Tools    │
└─────────┴────────────────────────┴───────────┘
```

## STORES

| Store | Purpose |
|-------|---------|
| `useAuthStore` | User session, login/logout |
| `useChatStore` | Messages, streaming, typing state |
| `useWorkspaceStore` | Project context, mounted files, active tool |
| `useUIStore` | Overlay visibility |
| `useTaskStore` | Task queue state |

## API INTEGRATION

```typescript
// src/lib/api.ts
const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
// Token auto-injected from localStorage('autonome_access_token')
// 401 → auto-redirect to /login
```

## COMMANDS

```bash
npm run dev      # Development (port 3000)
npm run build    # Production build (standalone output)
npm run start    # Production server
npm run lint     # ESLint
```
