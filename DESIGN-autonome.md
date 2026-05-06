---
version: alpha
name: Autonome Studio
description: AI-Native Bioinformatics IDE — a dark-first developer tool interface built on Tailwind CSS v4 + shadcn/ui New York style. Geist Sans typography with OKLCH color primitives and a sidebar-driven workspace architecture. Every interaction surface is a capsule or a ghost, with semantic color accents (blue/emerald/purple) tagging distinct functional domains.
colors:
  background: "oklch(0.129 0.042 264.695)"
  foreground: "oklch(0.984 0.003 247.858)"
  card: "oklch(0.208 0.042 265.755)"
  card-foreground: "oklch(0.984 0.003 247.858)"
  popover: "oklch(0.208 0.042 265.755)"
  popover-foreground: "oklch(0.984 0.003 247.858)"
  primary: "oklch(0.929 0.013 255.508)"
  primary-foreground: "oklch(0.208 0.042 265.755)"
  secondary: "oklch(0.279 0.041 260.031)"
  secondary-foreground: "oklch(0.984 0.003 247.858)"
  muted: "oklch(0.279 0.041 260.031)"
  muted-foreground: "oklch(0.704 0.04 256.788)"
  accent: "oklch(0.279 0.041 260.031)"
  accent-foreground: "oklch(0.984 0.003 247.858)"
  destructive: "oklch(0.704 0.191 22.216)"
  destructive-foreground: "oklch(0.984 0.003 247.858)"
  border: "oklch(1 0 0 / 10%)"
  input: "oklch(1 0 0 / 15%)"
  ring: "oklch(0.551 0.027 264.364)"
  sidebar: "oklch(0.208 0.042 265.755)"
  sidebar-foreground: "oklch(0.984 0.003 247.858)"
  sidebar-primary: "oklch(0.488 0.243 264.376)"
  sidebar-primary-foreground: "oklch(0.984 0.003 247.858)"
  sidebar-accent: "oklch(0.279 0.041 260.031)"
  sidebar-accent-foreground: "oklch(0.984 0.003 247.858)"
  sidebar-border: "oklch(1 0 0 / 10%)"
  sidebar-ring: "oklch(0.551 0.027 264.364)"
  semantic-blue: "#2563eb"
  semantic-blue-hover: "#1d4ed8"
  semantic-blue-bg: "#1e3a5f"
  semantic-purple: "#a855f7"
  semantic-purple-hover: "#9333ea"
  semantic-emerald: "#10b981"
  semantic-emerald-hover: "#059669"
  semantic-amber: "#f59e0b"
  semantic-rose: "#f43f5e"
  semantic-rose-hover: "#e11d48"
  semantic-violet: "#8b5cf6"
  semantic-violet-bg: "rgb(139 92 246 / 0.1)"
  semantic-cyan: "#06b6d4"
  semantic-green: "#22c55e"
  semantic-green-hover: "#16a34a"
  semantic-yellow: "#eab308"
  code-bg: "oklch(0.279 0.041 260.031)"
  chat-bg-light: "#ffffff"
  chat-bg-dark: "#131314"
  sidebar-bg-light: "#f9fafb"
  sidebar-bg-dark: "#1e1e20"
  sidebar-border-light: "#e5e7eb"
  sidebar-border-dark: "#2d2d30"
  header-height: 56px
  toast-bg: "#1a1a1a"
  toast-border: "#333333"
  toast-text: "#e5e5e5"

typography:
  font-sans:
    fontFamily: "Geist Sans, ui-sans-serif, system-ui, -apple-system, sans-serif"
  font-mono:
    fontFamily: "Geist Mono, ui-monospace, SFMono-Regular, monospace"
  micro:
    fontSize: 10px
    fontWeight: 400
    lineHeight: 1.0
    usage: "Badge labels, status indicators, shortcut hints"
  caption-legal:
    fontSize: 11px
    fontWeight: 400
    lineHeight: 1.2
    usage: "Avatar initials, tag filter pills, section group headers"
  caption:
    fontSize: 12px
    fontWeight: 400
    lineHeight: 1.3
    usage: "Session items, secondary labels, credits display"
  caption-strong:
    fontSize: 13px
    fontWeight: 500
    lineHeight: 1.4
    usage: "Menu items, session titles, file paths, tool descriptions"
  body-small:
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.4
    usage: "Input text, button labels, form controls"
  body:
    fontSize: 16px
    fontWeight: 400
    lineHeight: 2.0
    letterSpacing: 0.01em
    usage: "Chat message body copy"
  body-strong:
    fontSize: 16px
    fontWeight: 500
    lineHeight: 1.5
    usage: "Emphasized chat content"
  chat-heading-h1:
    fontSize: 24px
    fontWeight: 600
    lineHeight: 1.5
    usage: "Chat message h1"
  chat-heading-h2:
    fontSize: 20px
    fontWeight: 600
    lineHeight: 1.5
    usage: "Chat message h2"
  chat-heading-h3:
    fontSize: 18px
    fontWeight: 600
    lineHeight: 1.5
    usage: "Chat message h3"
  section-heading:
    fontSize: 20px
    fontWeight: 600
    lineHeight: 1.4
    usage: "Section headers in panels"
  modal-title:
    fontSize: 18px
    fontWeight: 600
    lineHeight: 1.4
    usage: "Modal and overlay titles"
  welcome-heading:
    fontSize: 30px
    fontWeight: 700
    lineHeight: 1.2
    usage: "Welcome screen greeting"
  welcome-heading-lg:
    fontSize: 36px
    fontWeight: 700
    lineHeight: 1.2
    usage: "Large welcome screen greeting"
  code-inline:
    fontSize: 0.875em
    fontFamily: "Geist Mono"
    usage: "Inline code in chat messages"
  code-block:
    fontSize: 14px
    lineHeight: 1.6
    fontFamily: "Geist Mono"
    usage: "Code blocks in chat messages"
  table-header:
    fontSize: 13px
    fontWeight: 600
    letterSpacing: 0.05em
    textTransform: uppercase
    usage: "Table headers"
  table-cell:
    fontSize: 15px
    fontWeight: 400
    usage: "Table body cells"
  nav-item:
    fontSize: 13px
    fontWeight: 500
    lineHeight: 1.4
    usage: "Sidebar navigation items"
  tag-pill:
    fontSize: 11px
    fontWeight: 500
    lineHeight: 1.0
    usage: "Tag filter pills"
  mode-switcher:
    fontSize: 12px
    fontWeight: 500
    lineHeight: 1.0
    usage: "Top header mode switcher"

rounded:
  none: 0px
  sm: 2px
  md: 6px
  lg: 8px
  xl: 12px
  2xl: 16px
  3xl: 22px
  full: 9999px

spacing:
  xs: 4px
  sm: 6px
  md: 8px
  lg: 12px
  xl: 16px
  xxl: 20px
  section: 24px
  large: 32px

shadows:
  sm: "0 1px 2px 0 rgb(0 0 0 / 0.05)"
  md: "0 4px 6px -1px rgb(0 0 0 / 0.1)"
  lg: "0 10px 15px -3px rgb(0 0 0 / 0.1)"
  xl: "0 20px 25px -5px rgb(0 0 0 / 0.1)"
  2xl: "0 25px 50px -12px rgb(0 0 0 / 0.25)"
  inner: "inset 0 2px 4px 0 rgb(0 0 0 / 0.05)"
  glow-blue: "0 0 15px rgba(6, 182, 212, 0.15)"
  glow-purple: "0 0 15px rgba(168, 85, 247, 0.15)"
  ai-breathing: "0 0 15px-30px oscillation blue glow"

components:
  button-primary:
    backgroundColor: "{colors.semantic-blue}"
    hoverBackgroundColor: "{colors.semantic-blue-hover}"
    textColor: "#ffffff"
    rounded: "{rounded.full}"
    padding: 8px 16px
    fontSize: "{typography.body-small.fontSize}"
    fontWeight: 500
    transition: "colors"
  button-primary-large:
    backgroundColor: "{colors.semantic-blue}"
    hoverBackgroundColor: "blue-500"
    textColor: "#ffffff"
    rounded: "{rounded.lg}"
    padding: 8px 20px
    fontSize: "{typography.body-small.fontSize}"
    fontWeight: 500
    shadow: "{shadows.lg}"
    shadowColor: "blue-900/20"
  button-secondary:
    backgroundColor: "{colors.secondary}"
    hoverBackgroundColor: "neutral-800/60"
    textColor: "neutral-300"
    rounded: "{rounded.lg}"
    padding: 10px 12px
    fontSize: "{typography.nav-item.fontSize}"
    fontWeight: 500
  button-ghost:
    backgroundColor: transparent
    hoverBackgroundColor: "neutral-800/50"
    textColor: "neutral-300"
    hoverTextColor: "#ffffff"
    rounded: "{rounded.lg}"
    padding: 6px
    fontSize: "{typography.nav-item.fontSize}"
  button-icon:
    backgroundColor: transparent
    textColor: "neutral-500"
    hoverTextColor: "neutral-200"
    hoverBackgroundColor: "neutral-800/50"
    rounded: "{rounded.md}"
    padding: 6px
    size: 28px
  button-destructive:
    backgroundColor: transparent
    textColor: "{colors.semantic-rose}"
    hoverTextColor: "rose-300"
    hoverBackgroundColor: "rose-500/10"
    rounded: "{rounded.lg}"
    transition: "colors"
  button-stop:
    backgroundColor: "red-500"
    hoverBackgroundColor: "red-600"
    textColor: "#ffffff"
    rounded: "{rounded.full}"
    padding: 8px
  button-purple:
    backgroundColor: "{colors.semantic-purple}"
    hoverBackgroundColor: "{colors.semantic-purple-hover}"
    textColor: "#ffffff"
    rounded: "{rounded.lg}"
    padding: 8px 20px
    fontSize: "{typography.body-small.fontSize}"
    fontWeight: 500
    shadow: "{shadows.lg}"
    shadowColor: "purple-900/20"
  button-green:
    backgroundColor: "{colors.semantic-green}"
    hoverBackgroundColor: "{colors.semantic-green-hover}"
    textColor: "#ffffff"
    rounded: "{rounded.lg}"
    padding: 8px 16px
    fontSize: "{typography.body-small.fontSize}"
  tag-pill-selected:
    backgroundColor: "{colors.semantic-blue}"
    textColor: "#ffffff"
    fontSize: "{typography.tag-pill.fontSize}"
    rounded: "{rounded.full}"
    padding: 2px 8px
  tag-pill-unselected:
    backgroundColor: "neutral-800"
    textColor: "neutral-400"
    hoverBackgroundColor: "neutral-700"
    fontSize: "{typography.tag-pill.fontSize}"
    rounded: "{rounded.full}"
    padding: 2px 8px
  mode-switcher:
    backgroundColor: "neutral-900"
    textColor: "neutral-400"
    fontSize: "{typography.mode-switcher.fontSize}"
    rounded: "{rounded.full}"
    padding: 6px 12px
    borderWidth: 1px
    borderColor: "neutral-800"
  credits-badge:
    backgroundColor: "neutral-900"
    textColor: "neutral-400"
    fontSize: "{typography.caption.fontSize}"
    rounded: "{rounded.full}"
    padding: 6px 12px
    borderWidth: 1px
    borderColor: "neutral-800"
  tab-switcher-active:
    backgroundColor: "neutral-800"
    textColor: "#ffffff"
    fontSize: "{typography.body-small.fontSize}"
    fontWeight: 500
    rounded: "{rounded.md}"
    padding: 8px 16px
    shadow: "{shadows.sm}"
  tab-switcher-inactive:
    backgroundColor: transparent
    textColor: "neutral-500"
    hoverTextColor: "neutral-300"
    fontSize: "{typography.body-small.fontSize}"
    fontWeight: 500
    rounded: "{rounded.md}"
    padding: 8px 16px
  session-item:
    backgroundColor: "neutral-800"
    hoverBackgroundColor: "neutral-700"
    textColor: "neutral-300"
    fontSize: "{typography.caption.fontSize}"
    rounded: "{rounded.md}"
    padding: 6px 12px
    borderWidth: 1px
    borderColor: "neutral-700/50"
    shadow: "{shadows.sm}"
  nav-item-active-data:
    backgroundColor: "{colors.semantic-purple}"
    textColor: "#ffffff"
    rounded: "{rounded.lg}"
    padding: 10px 12px
    glowShadow: "{shadows.glow-purple}"
  nav-item-active-skill:
    backgroundColor: "{colors.semantic-blue}"
    textColor: "#ffffff"
    rounded: "{rounded.lg}"
    padding: 10px 12px
    glowShadow: "{shadows.glow-blue}"
  nav-item-active-learning:
    backgroundColor: "{colors.semantic-emerald}"
    textColor: "#ffffff"
    rounded: "{rounded.lg}"
    padding: 10px 12px
  chat-input:
    backgroundColor: "{colors.chat-bg-dark}"
    borderWidth: 1px
    borderColor: "neutral-700/50"
    rounded: "{rounded.2xl}"
    maxWidth: 896px
    shadow: "{shadows.lg}"
  chat-message-ai:
    backgroundColor: transparent
    textColor: "{colors.foreground}"
    fontSize: "{typography.body.fontSize}"
    lineHeight: "{typography.body.lineHeight}"
    letterSpacing: "{typography.body.letterSpacing}"
  chat-message-code:
    backgroundColor: "{colors.code-bg}"
    fontSize: "{typography.code-block.fontSize}"
    lineHeight: "{typography.code-block.lineHeight}"
    rounded: 0.75em
  sidebar:
    width: 224px
    backgroundColor: "{colors.sidebar-bg-dark}"
    borderRightWidth: 1px
    borderRightColor: "{colors.sidebar-border-dark}"
  top-header:
    height: "{colors.header-height}"
    backgroundColor: transparent
    borderBottomWidth: 0
  overlay-panel:
    backgroundColor: "neutral-950"
    width: "85vw"
    maxWidth: 1152px
    rounded: "{rounded.xl}"
    shadow: "{shadows.2xl}"
    animation: "spring, slide-in-right"
  mobile-nav:
    position: fixed
    bottom: 0
    height: 64px
    backgroundColor: "neutral-900"
    borderTopWidth: 1px
    borderTopColor: "neutral-800"
    zIndex: 40
  toast:
    backgroundColor: "{colors.toast-bg}"
    borderWidth: 1px
    borderColor: "{colors.toast-border}"
    textColor: "{colors.toast-text}"
    position: top-right
    duration: 5000ms
  scrollbar:
    width: 6px
    trackColor: transparent
    thumbColor: "rgba(255, 255, 255, 0.1)"
    thumbHoverColor: "rgba(255, 255, 255, 0.2)"
    borderRadius: 10px
  dropdown-menu:
    backgroundColor: "neutral-900"
    borderWidth: 1px
    borderColor: "neutral-800"
    rounded: "{rounded.xl}"
    shadow: "{shadows.2xl}"
    animation: "spring, scale 0.95 -> 1, y 10 -> 0"
  modal:
    backgroundColor: "neutral-900"
    borderWidth: 1px
    borderColor: "neutral-800"
    rounded: "{rounded.xl}"
    shadow: "{shadows.2xl}"
    animation: "spring, stiffness 200, damping 25"
  deep-think-toggle:
    backgroundColor: transparent
    textColor: "neutral-500"
    activeTextColor: "{colors.semantic-violet}"
    activeBackgroundColor: "{colors.semantic-violet-bg}"
    rounded: "{rounded.full}"
    padding: 8px
---

## Overview

Autonome Studio is an **AI-native bioinformatics IDE** — a dark-first, developer-tool interface built on Tailwind CSS v4 and shadcn/ui New York style. Its interface is organized around a persistent left sidebar that acts as the primary navigation hub, a top header for context display, and a central chat canvas powered by the Vercel AI SDK. Overlay panels slide in from the right for specialized workspaces (data browsing, skill marketplace, project management).

The design language is capsule-centric: buttons, tags, mode switchers, and credits badges all share the `rounded-full` pill form. Semantic color accents tag distinct functional domains — blue for AI/chat, purple for data, emerald for learning, amber for status, rose for destructive actions. The interface defaults to dark mode with Geist Sans typography, using OKLCH color space primitives and a restrained gray-blue neutral palette.

**Key Characteristics:**
- Dark-first interface with system-level light mode support; dark is the default and primary design target.
- Sidebar-driven workspace: 224px left sidebar with semantic color-coded navigation items.
- Capsule grammar: `rounded-full` pills for buttons, tags, badges, and mode switchers — the pill is the brand's interactive shape signal.
- Five semantic accent colors map to functional domains: blue (AI/actions), purple (data), emerald (learning), amber (status), rose (danger).
- Geist Sans as the sole typeface, paired with Geist Mono for code — no secondary brand font.
- Framer Motion spring animations on modals, dropdowns, and overlay panels.
- Overlay panel system: specialized workspaces slide in from the right as 85vw panels with glass-dark backgrounds.
- No decorative gradients; the grid-pattern background mask is the sole texture element.
- AI breathing glow: a `box-shadow` pulse animation on the chat input signals active AI processing.
- Touch-friendly mobile adaptation: bottom nav bar + slide-in sidebar sheet below 768px.

## Colors

### Primitives (OKLCH)

All theme tokens use the OKLCH color space, defined as CSS custom properties with Tailwind CSS v4 `@theme inline` mapping. The palette is anchored on a dark blue-gray base with near-white foreground, producing a low-contrast dark-mode reading experience.

| Token | Light Value | Dark Value | Role |
|-------|-------------|------------|------|
| `--background` | `oklch(1 0 0)` | `oklch(0.129 0.042 264.695)` | Page background |
| `--foreground` | `oklch(0.129 0.042 264.695)` | `oklch(0.984 0.003 247.858)` | Primary text |
| `--card` | `oklch(1 0 0)` | `oklch(0.208 0.042 265.755)` | Card surfaces |
| `--popover` | `oklch(1 0 0)` | `oklch(0.208 0.042 265.755)` | Dropdown/popover surfaces |
| `--primary` | `oklch(0.208 0.042 265.755)` | `oklch(0.929 0.013 255.508)` | Primary action (inverts light↔dark) |
| `--secondary` | `oklch(0.968 0.007 247.896)` | `oklch(0.279 0.041 260.031)` | Secondary surfaces |
| `--muted` | `oklch(0.968 0.007 247.896)` | `oklch(0.279 0.041 260.031)` | Muted backgrounds |
| `--muted-foreground` | `oklch(0.554 0.046 257.417)` | `oklch(0.704 0.04 256.788)` | Secondary text |
| `--accent` | `oklch(0.968 0.007 247.896)` | `oklch(0.279 0.041 260.031)` | Accent surfaces |
| `--destructive` | `oklch(0.577 0.245 27.325)` | `oklch(0.704 0.191 22.216)` | Destructive actions |
| `--border` | `oklch(0.929 0.013 255.508)` | `oklch(1 0 0 / 10%)` | Borders (transparent in dark) |
| `--input` | `oklch(0.929 0.013 255.508)` | `oklch(1 0 0 / 15%)` | Input borders |
| `--ring` | `oklch(0.704 0.04 256.788)` | `oklch(0.551 0.027 264.364)` | Focus rings |
| `--sidebar` | `oklch(0.984 0.003 247.858)` | `oklch(0.208 0.042 265.755)` | Sidebar background |
| `--sidebar-primary` | `oklch(0.208 0.042 265.755)` | `oklch(0.488 0.243 264.376)` | Sidebar active item |
| `--sidebar-accent` | `oklch(0.968 0.007 247.896)` | `oklch(0.279 0.041 260.031)` | Sidebar hover |
| `--sidebar-border` | `oklch(0.929 0.013 255.508)` | `oklch(1 0 0 / 10%)` | Sidebar divider |

### Semantic Accents

Beyond the OKLCH theme variables, five fixed-color semantic accents tag functional domains. These are applied as Tailwind utility classes directly, not as CSS custom properties.

| Color | Hex | Domain |
|-------|-----|--------|
| Blue | `#2563eb` (blue-600) → `#1d4ed8` (blue-700 hover) | Primary actions, AI chat, send button, skill center nav |
| Purple | `#a855f7` (purple-500) → `#9333ea` (purple-600 hover) | Data center, create actions, sync |
| Emerald | `#10b981` (emerald-500) → `#059669` (emerald-600 hover) | Learning center, success states |
| Amber | `#f59e0b` (amber-500) | Status indicators, tab highlights |
| Rose | `#f43f5e` (rose-500) → `#e11d48` (rose-600 hover) | Logout, destructive actions, stop button |

**Additional color accents:**
- **Violet** (`#8b5cf6`): Deep think toggle active state.
- **Cyan** (`#06b6d4`): Data center icon badge glow.
- **Green** (`#22c55e`): Code import button.
- **Yellow** (`#eab308`): Credits/balance display.
- **Indigo** (`#6366f1`): User avatar gradient.

### Surface Constants

Used outside the theme variable system as Tailwind arbitrary values:

| Token | Value | Usage |
|-------|-------|-------|
| Chat background (dark) | `#131314` | Main chat area background |
| Sidebar background (dark) | `#1e1e20` | Left sidebar |
| Sidebar border (dark) | `#2d2d30` | Sidebar right border |
| Sidebar background (light) | `#f9fafb` (gray-50) | Left sidebar light mode |
| Overlay panel background | `neutral-950` | All slide-in overlay panels |
| Toast background | `#1a1a1a` | Sonner toast container |

### Background Effects

- **Grid pattern**: A 40×40px grid of 1px translucent white lines, masked with a vertical fade (`mask-image: linear-gradient(to bottom, transparent, black, transparent)`). Used on welcome and empty states.
- **AI breathing glow**: A CSS `glow-pulse` keyframe animation oscillating `box-shadow` from `0 0 15px` to `0 0 30px` in blue, over 3 seconds. Applied to the chat input card when the AI is processing.
- **Shimmer**: A sweeping light effect (`translateX(-100%)` → `translateX(400%)`) over 1.5s for loading skeletons.
- **No gradients**: The system uses flat colors exclusively. Atmosphere comes from the grid pattern and glow animations rather than CSS gradients.

## Typography

### Font Family

- **Sans-serif**: Geist Sans — Vercel's open-source typeface, loaded via Next.js `next/font/google`. Used for all UI text, navigation, buttons, and chat body copy.
- **Monospace**: Geist Mono — Vercel's open-source monospace. Used for code blocks, inline code, and file paths.
- **Fallback stack**: `ui-sans-serif, system-ui, -apple-system, sans-serif` for Geist Sans; `ui-monospace, SFMono-Regular, monospace` for Geist Mono.

### Hierarchy

| Token | Size | Weight | Line Height | Letter Spacing | Use |
|-------|------|--------|-------------|----------------|-----|
| `{typography.welcome-heading-lg}` | 36px | 700 | 1.2 | 0 | Large welcome screen greeting |
| `{typography.welcome-heading}` | 30px | 700 | 1.2 | 0 | Welcome screen greeting |
| `{typography.chat-heading-h1}` | 24px | 600 | 1.5 | 0 | Chat message h1 |
| `{typography.chat-heading-h2}` | 20px | 600 | 1.5 | 0 | Chat message h2 |
| `{typography.modal-title}` | 18px | 600 | 1.4 | 0 | Modal and overlay panel titles |
| `{typography.chat-heading-h3}` | 18px | 600 | 1.5 | 0 | Chat message h3 |
| `{typography.body}` | 16px | 400 | 2.0 | 0.01em | Chat message body copy |
| `{typography.body-small}` | 14px | 400 | 1.4 | 0 | Input text, button labels, form controls |
| `{typography.caption-strong}` | 13px | 500 | 1.4 | 0 | Menu items, session titles, file paths |
| `{typography.table-header}` | 13px | 600 | 1.4 | 0.05em | Table headers (uppercase) |
| `{typography.table-cell}` | 15px | 400 | 1.4 | 0 | Table body cells |
| `{typography.caption}` | 12px | 400 | 1.3 | 0 | Session items, credits display |
| `{typography.tag-pill}` | 11px | 500 | 1.0 | 0 | Tag filter pills |
| `{typography.caption-legal}` | 11px | 400 | 1.2 | 0 | Section group headers, avatar initials |
| `{typography.micro}` | 10px | 400 | 1.0 | 0 | Badge labels, status indicators, shortcut hints |
| `{typography.code-block}` | 14px | 400 | 1.6 | 0 | Code blocks (Geist Mono) |
| `{typography.code-inline}` | 0.875em | 400 | 1.0 | 0 | Inline code (Geist Mono) |

### Principles

- **Single typeface family.** Geist Sans for UI, Geist Mono for code. No secondary brand font. No serif. No weight 300 or 800 — the ladder is 400 / 500 / 600 / 700.
- **Chat body at 16px with generous leading.** Paragraph text in chat messages uses 16px / 400 weight / 2.0 line-height / 0.01em letter-spacing. The 2.0 leading creates an editorial reading pace in the AI conversation.
- **Weight 500 is the UI workhorse.** Navigation items, menu entries, session titles all use weight 500 — lighter than 600 headings but heavier than 400 body.
- **Table headers uppercase with tracking.** 13px / 600 weight / 0.05em letter-spacing / uppercase transform — the only place uppercase is used systematically.
- **Code is 14px with 1.6 leading.** Slightly smaller than body text (16px), with tighter but still breathable leading.
- **Weight 700 reserved for welcome headings only.** The largest display text (30–36px) uses weight 700 to create a bold entry point; all other headings use 600.
- **No italic, no underline (except links).** Emphasis is conveyed through weight changes (400 → 500 → 600), not style variants.

### Note on Font Substitutes

Geist Sans is Vercel's open-source typeface available on Google Fonts. For off-system builds:
- Use `Inter` as the closest open-source alternative — both share the geometric-sans DNA and similar x-height.
- Inter at weight 500 approximates Geist Sans 500; Inter at 600 approximates Geist Sans 600.
- For code, `JetBrains Mono` is the closest match to Geist Mono's character width and ligature behavior.

## Layout

### Spacing System

The spacing scale follows Tailwind CSS v4 defaults (4px base unit). Common structural values:

| Token | Value | Usage |
|-------|-------|-------|
| `{spacing.xs}` | 4px | Tight icon groups, tag pill padding, close button gaps |
| `{spacing.sm}` | 6px | Button icon padding, small button padding |
| `{spacing.md}` | 8px | Standard button padding, icon padding, nav item gaps |
| `{spacing.lg}` | 12px | Section padding, nav section spacing, card padding |
| `{spacing.xl}` | 16px | Modal padding, chat input padding, section spacing |
| `{spacing.xxl}` | 20px | Larger button horizontal padding |
| `{spacing.section}` | 24px | Card inner spacing, modal padding |
| `{spacing.large}` | 32px | Extra large section padding |

**Structural constants:**
- Sidebar width: 224px (`w-56`)
- Top header height: 56px (`h-14`)
- Mobile bottom nav height: 64px
- Chat input max-width: 896px (`max-w-4xl`) in conversation mode, 768px (`max-w-3xl`) in welcome mode
- Overlay panel width: 85vw, max 1152px (`max-w-6xl`)
- Data Center panel width: 900px fixed on desktop

### Grid & Container

- **No global max-width container.** The chat canvas fills available space between the sidebar and the right edge. Chat messages are centered with `max-w-4xl` (896px) and horizontal auto margins.
- **Sidebar + content + overlay pattern.** The main layout is a horizontal three-zone system:
  1. Left sidebar (224px, shrink-0, border-r)
  2. Central chat area (flex-1, overflow-hidden)
  3. Right overlay panels (z-50, slide-in)
- **No multi-column content grids.** The interface is fundamentally single-column: sidebar navigation → chat canvas → overlay panels. Card grids appear only inside overlay panels (Data Center, Skill Center).
- **Mobile collapses to stack.** Below 768px, the sidebar becomes a slide-in sheet, the top header simplifies, and a fixed bottom nav bar appears.

### Whitespace Philosophy

The interface is vertically compact — a developer tool aesthetic where information density is valued over breathing room. Panel sections use 12–16px gaps. Chat messages have tight vertical rhythm (the 2.0 line-height on 16px body creates natural paragraph separation). The welcome screen is the only "airy" surface, with centered hero content in an otherwise empty viewport.

## Elevation & Depth

| Level | Treatment | Use |
|-------|-----------|-----|
| Flat | No shadow, flat color | Chat area, sidebar, top header, body content |
| Subtle | `shadow-sm` (0 1px 2px) | Session items, active tabs |
| Medium | `shadow-md` (0 4px 6px) | Chat input card, hover states |
| Elevated | `shadow-lg` (0 10px 15px) | Action buttons with colored shadow tints |
| Floating | `shadow-xl` (0 20px 25px) | Dropdown menus (dark mode) |
| Modal | `shadow-2xl` (0 25px 50px) | All overlay panels, modals, dropdown menus |
| Inner | `shadow-inner` (inset 0 2px 4px) | Active/pressed capsule buttons |
| Glow | `0 0 15px` colored | Active nav item badges (cyan for data, purple for skill center) |
| AI Pulse | `0 0 15→30px` oscillating | Chat input during AI processing |

**Shadow philosophy.** The system uses Tailwind's default shadow scale progressively: light touch for interactive elements (session items, tabs), heavier for floating surfaces (modals, dropdowns). Colored shadows (`shadow-blue-900/20`, `shadow-purple-900/20`) tint action buttons to reinforce the semantic accent system. The AI breathing glow is the only animated shadow — it signals system activity, not hierarchy.

**No backdrop-blur.** Unlike Apple's frosted glass, Autonome uses opaque dark surfaces for all panels and overlays. Separation comes from shadow depth and border hairlines, not transparency effects.

## Shapes

### Border Radius Scale

| Token | Value | Usage |
|-------|-------|-------|
| `{rounded.none}` | 0px | Sharp containers (rare) |
| `{rounded.sm}` | 2px | Nested inner elements |
| `{rounded.md}` | 6px | Buttons, input fields, session items, tab switcher |
| `{rounded.lg}` | 8px | Navigation items, menu items, secondary buttons |
| `{rounded.xl}` | 12px | Modals, dropdown menus, cards, file pickers |
| `{rounded.2xl}` | 16px | Chat input box, large preview modals, project cards |
| `{rounded.3xl}` | 22px | (defined, rarely used) |
| `{rounded.full}` | 9999px | Primary action buttons, tag pills, mode switcher, credits badge, avatars — the capsule grammar |

**Code block rounding.** Syntax-highlighted code blocks use `0.75em` (~12px) border-radius independently of the system scale.

**Scrollbar thumb.** Uses a custom `10px` border-radius, matched to the 6px scrollbar width for a fully rounded thumb.

### Capsule Grammar

The `rounded-full` pill is the dominant interactive shape. It appears on:
- Primary action buttons (send, stop)
- Tag filter pills (selected and unselected)
- Mode switcher (top header)
- Credits badge (top header)
- Avatar containers
- Deep think toggle
- Action menu triggers
- Configurator option chips (skill center)

The capsule is the system's "this is interactive" signal — equivalent to Apple's blue pill accent. Rectangular rounding (`rounded-lg`, `rounded-xl`) is reserved for containers (modals, cards, dropdowns), while the pill marks actions.

### Icon & Avatar Geometry

- **Avatars**: Circular (`rounded-full`), 24–32px, with indigo gradient background (`from-indigo-400 to-indigo-500`). User initials at 11px.
- **Navigation icons**: 16–18px Lucide icons, consistent stroke width. Colored by semantic domain (blue, purple, emerald, amber, rose) or neutral (gray-400, neutral-500).
- **Circular control chips**: 28–44px touch targets for icon-only buttons (`button-icon`).
- **No rounded imagery**: Product images, project thumbnails use `rounded-lg` (8px) or `rounded-md` (6px) — never full-bleed.

## Components

### Top Navigation

**`top-header`** — Persistent slim header bar pinned to the top of the main content area. Height 56px, horizontal padding 12–16px. Background transparent (inherits chat area background). Left: mobile menu button (below 768px) + project breadcrumb ("Projects > ProjectName"). Right cluster: mode switcher (compact capsule), credits badge (yellow icon + balance number), share/export menu. No bottom border — the header floats cleanly above the chat canvas.

**`mode-switcher`** — A compact pill in the top header: `rounded-full`, `bg-neutral-900`, 1px `border-neutral-800`, text `neutral-400` at 12px. Displays current AI mode (e.g., "Claude", "Auto") with a dropdown to switch. Active state: subtle background shift.

### Sidebar

**`sidebar`** — Persistent left sidebar, 224px wide, shrink-0. Background `#1e1e20` (dark) / `#f9fafb` (light). Right border 1px `#2d2d30` (dark) / `#e5e7eb` (light). Hidden below 768px (replaced by `mobile-sidebar-sheet`).

Sections (top to bottom):
1. **Logo**: Height 56px, bottom border. Displays "AUTONOME" brand name with DNA emoji icon.
2. **Main navigation**: `p-3`, `space-y-1`. Seven nav items with Lucide icons + labels at 13px / 500 weight. Default: `text-neutral-300`, `hover:bg-neutral-800/50`, `rounded-lg`. Active states use full semantic color fills.
3. **Session list**: `flex-1` with top border divider. Tag filter pills at top, then session items grouped by time period (Today, Previous 7 Days, Older). Each session: `rounded-md`, `bg-neutral-800`, 1px border, 12px label.
4. **User capsule**: `p-3`, `mt-auto`. Shows user email, credit balance, theme toggle (sun/moon). Expands to popover menu with User Center, Admin Console (shield icon, yellow), Logout (rose).

### Navigation Active States

| Nav Item | Active Background | Active Glow |
|----------|------------------|-------------|
| Control Panel | `neutral-800` (default) | none |
| Project Center | `neutral-800` (default) | none |
| Task Center | `neutral-800` (default) | none |
| Data Center | `purple-600` | `0 0 15px rgba(168, 85, 247, 0.15)` |
| Skill Center | `blue-600` | `0 0 15px rgba(6, 182, 212, 0.15)` |
| Learning Center | `emerald-600` | none |
| Terminal | `neutral-800` (default) | none |

### Buttons

**`button-primary`** — The primary action button. `bg-blue-600`, `hover:bg-blue-700`, white text, `rounded-full`, padding 8px × 16px, 14px / 500 weight. Used for send, submit, and primary CTAs. Dark mode variant: `bg-white`, `text-black`, `hover:bg-neutral-200` (inverted contrast for the send button specifically).

**`button-primary-large`** — Extended primary action. `bg-blue-600`, `rounded-lg` (not pill), padding 8px × 20px, `shadow-lg shadow-blue-900/20`. Used for modal confirmations and overlay panel actions.

**`button-stop`** — The stop/interrupt action. `bg-red-500`, `hover:bg-red-600`, white text, `rounded-full`, padding 8px. Used during AI streaming to interrupt generation.

**`button-purple`** — Data center and creation actions. `bg-purple-600`, `hover:bg-purple-500`, white text, `rounded-lg`, padding 8px × 20px, `shadow-lg shadow-purple-900/20`.

**`button-green`** — Code import and success actions. `bg-green-600`, `hover:bg-green-500`, white text, `rounded-lg`, padding 8px × 16px.

**`button-ghost`** — Navigation items and menu entries. Transparent background, `hover:bg-neutral-800/50`, `text-neutral-300` → `hover:text-white`, `rounded-lg`, padding 6–10px, 13px / 500 weight.

**`button-icon`** — Icon-only controls. Transparent, `text-neutral-500` → `hover:text-neutral-200`, `hover:bg-neutral-800/50`, `rounded-md`, padding 6px, 28px minimum touch target.

**`button-destructive`** — Logout and delete actions. Transparent, `text-rose-400` → `hover:text-rose-300`, `hover:bg-rose-500/10`, `rounded-lg`.

**`deep-think-toggle`** — AI reasoning toggle. Transparent, `text-neutral-500`, `hover:text-violet-500`, `hover:bg-violet-500/10`, `rounded-full`. Active: `text-violet-500`, `bg-violet-500/10`.

**Active/Press state.** All buttons use Tailwind `transition-colors` for smooth color transitions. No `transform: scale()` press effect — the system relies on color shifts rather than scale micro-interactions.

**Disabled state.** `bg-gray-300` (light) / `bg-neutral-800` (dark), `text-neutral-500`, no hover effects.

### Session Items

**`session-item`** — Chat session entry in the sidebar. `bg-neutral-800`, `hover:bg-neutral-700`, 1px `border-neutral-700/50`, `rounded-md`, `shadow-sm`. Contains session title (12px / 400, truncated), message count, and action buttons (rename, delete) on hover. Active session: elevated background contrast.

**`tag-pill-selected`** — Active tag filter. `bg-blue-500`, white text, 11px / 500, `rounded-full`, padding 2px × 8px.

**`tag-pill-unselected`** — Inactive tag filter. `bg-neutral-800` (dark) / `bg-gray-100` (light), `text-neutral-400` (dark) / `text-gray-600` (light), `hover:bg-neutral-700` (dark) / `hover:bg-gray-200` (light).

### Chat Interface

**`chat-canvas`** — Central message area. Background `#131314` (dark) / `#ffffff` (light). Vertical flex layout: messages fill available space, input area shrinks to content.

**`chat-message-ai`** — AI response bubble. No background card — messages float directly on the canvas. Body text at 16px / 400 / 2.0 leading / 0.01em tracking. Markdown rendering with heading support (h1–h3 at 24/20/18px, 600 weight), tables (13px headers uppercase, 15px cells), code blocks (14px Geist Mono, 1.6 leading, `0.75em` radius, `bg-neutral-800`), and inline code (0.875em Geist Mono).

**`chat-message-user`** — User message. Same canvas-floating style as AI messages. Right-aligned or distinguished by a subtle background tint.

**`chat-input`** — Bottom input area. Background matches canvas, `rounded-2xl` (16px), 1px border `neutral-700/50`, `shadow-lg` (dark: `shadow-xl`), `max-w-4xl` centered. Contains: textarea input → attachment menu (paperclip icon) → skill menu (box icon) → code import (code icon) → deep think toggle (brain icon) → send/stop button. Below input: fine-print disclaimer text and model attribution.

**`streaming-cursor`** — Blinking cursor during AI streaming. CSS `cursor-blink` animation (1s step-end), rendered as an inline block element at the end of streaming text.

**`virtualized-message-list`** — Messages rendered via `@tanstack/react-virtual` for performance. Each message is wrapped in `MemoizedMessageItem` with React.memo to prevent re-renders.

### Overlay Panels

**`overlay-panel`** — Slide-in panel from the right. `bg-neutral-950`, width `85vw` (max 1152px), `rounded-xl`, `shadow-2xl`. Framer Motion spring animation: `x: "100%" → 0`, stiffness 200, damping 25. Backdrop: semi-transparent overlay behind panel, click-to-dismiss.

**Panel types:**
- **Data Center** (`w-[900px]`): Genome browser, database tables, custom fields. Three-tab layout with file tree + data grid.
- **Skill Center**: Skill marketplace, execution panel, my skills, forge, settings. Five-tab layout.
- **Project Center**: Project list, create project, project settings.
- **Task Center**: Task queue, execution history, task details.
- **Control Panel** (`w-[95vw] md:w-[1200px]`): System controls and configuration.
- **User Center**: Profile, wallet/top-up, security settings, RBAC, AI model settings, keyboard shortcuts.
- **Learning Center**: Learning resources with emerald accent.
- **Web Terminal**: xterm.js terminal emulator, full dark background.
- **Settings Center**: Application settings.
- **Forge Overlay**: Skill creation and editing.
- **Package Manager**: Package installation and management.

### Mobile Components

**`mobile-nav`** — Fixed bottom navigation bar, visible below 768px. `bg-neutral-900`, 1px top border `neutral-800`, 64px height, `z-40`. Four tabs with Lucide icons + labels: Chat, Project, Data, Skill. Active tab: `text-white`, inactive: `text-neutral-500`. No text labels — icon-only on small screens.

**`mobile-sidebar-sheet`** — Animated slide-in drawer from the left edge. Replaces the desktop sidebar. Framer Motion animation, overlay backdrop, swipe-to-dismiss gesture support.

**Mobile touch targets.** All interactive elements below 768px enforce `min-height: 44px; min-width: 44px` via a CSS rule targeting `button:not(.compact)`, `a:not(.compact)`, and `[role="button"]:not(.compact)`.

### Modals & Dialogs

**`modal`** — Centered modal dialog. `bg-neutral-900`, 1px `border-neutral-800`, `rounded-xl`, `shadow-2xl`. Framer Motion spring animation: `scale: 0.95 → 1`, `opacity: 0 → 1`, stiffness 200–300, damping 25. Backdrop overlay with click-to-dismiss.

**`dropdown-menu`** — Popover menu attached to trigger element. `bg-neutral-900`, 1px `border-neutral-800`, `rounded-xl`, `shadow-2xl`. Animation: `initial={{ opacity: 0, scale: 0.95, y: 10 }}`. Menu items: 13px / 500, `rounded-lg`, `hover:bg-neutral-800/60`, 6px vertical padding × 8px horizontal.

### Inputs & Forms

**`search-input`** — Accessory and data search. Pill-shaped (`rounded-full`), 1px transparent-white border, dark background. Leading search icon at 14px, muted tint. Used in session search, data center filter, and skill market search.

**`textarea-input`** — Chat message input. Multi-line textarea within the `chat-input` card. No visible border (inherits from card), transparent background, placeholder text in `neutral-500`. Auto-grows with content.

**`form-fields`** — Modal form inputs. `bg-neutral-800`, 1px `border-neutral-700`, `rounded-md`, 14px text. Focus: `ring-1 ring-blue-500/50`.

**`toggle-switch`** — Binary state toggle. Capsule track with circular thumb. Active: blue background. Inactive: neutral-700 background.

### Footer & Utility

**`chat-disclaimer`** — Fine-print text below the chat input. 11–12px, `text-neutral-500`, centered. States model name, capability limitations, and usage terms.

**`toast`** — Sonner toast notification. `bg-[#1a1a1a]`, 1px `border-[#333]`, `text-[#e5e5e5]`, `top-right` position, 5000ms duration. Rich colors enabled. Used for success, error, warning, and info feedback.

**`scrollbar`** — Custom thin scrollbar. 6px width/height, transparent track, `rgba(255, 255, 255, 0.1)` thumb (hover: `rgba(255, 255, 255, 0.2)`), 10px border-radius. Applied globally via `::-webkit-scrollbar` pseudo-elements and `scrollbar-width: thin` for Firefox.

**`grid-pattern-bg`** — Decorative texture. 40px × 40px grid of translucent white lines, masked with vertical fade gradient. Used on welcome screen and empty states to add visual interest without competing with content.

### AI-Specific Components

**`thinking-block`** — Collapsible section showing AI reasoning process. Darker background, left accent border in violet, collapsible with chevron toggle. Monospace or reduced-size text.

**`tool-use-block`** — Tool call display. Shows tool name, input parameters (collapsed by default), and output. Code-block styling with distinct header bar.

**`plan-card`** — Structured plan display. Card container with step list, status indicators (pending/in-progress/completed), progress bar.

**`task-card`** — Task display with status badge, title, and expandable details.

**`dag-progress-view`** — DAG workflow visualization using ReactFlow. Nodes show execution status with color coding (blue: pending, amber: running, emerald: complete, rose: failed). Edges show data flow dependencies.

**`streaming-markdown`** — Real-time markdown renderer for streaming AI responses. Incrementally renders partial markdown during token streaming. Supports GFM tables, KaTeX math, syntax-highlighted code blocks.

**`data-preview-card`** — Tabular data preview (pandas DataFrame style). Renders first N rows with column headers, data types, and shape summary.

**`interactive-plot-card`** — Interactive ECharts visualization. Supports zoom, pan, tooltip, and export. Responsive to container width.

## Responsive Behavior

### Breakpoints

| Name | Width | Key Changes |
|-------|-------|-------------|
| Small phone | < 420px | Single-column; sidebar hidden; bottom nav visible; chat input full-width |
| Phone | 420–640px | Single-column; overlay panels go full-screen |
| Tablet portrait | 641–768px | Sidebar remains hidden; overlay panels at 90vw |
| Tablet landscape / Small desktop | 769–1024px | Desktop sidebar visible (224px); overlay panels at 85vw; 3-column grids → 2-column |
| Desktop | 1025–1440px | Full layout; Data Center at 900px fixed; Control Panel at 1200px |
| Wide desktop | > 1440px | Content capped at panel max-widths; margins absorb extra width |

### Structural breakpoints for development: 768px (mobile↔desktop switch), 1024px (small desktop), 1440px (content lock).

### Touch Targets

- Minimum 44 × 44px on mobile (enforced via CSS rule).
- Desktop icon buttons: 28–32px minimum (developer tool density).
- Send/stop buttons: 40–44px diameter (`p-2` on 24px icon = ~40px).
- Nav items: full-width sidebar row, ~40px tall.

### Collapsing Strategy

- **Sidebar**: Persistent on desktop (≥ 768px) → hidden on mobile, replaced by `mobile-sidebar-sheet` (slide-in drawer) and `mobile-nav` (bottom bar).
- **Top header**: Full content (breadcrumb + mode + credits + share) on desktop → simplified (hamburger + project name) on mobile.
- **Overlay panels**: 85vw with max-width on desktop → full-screen on mobile.
- **Session list**: Visible inline in sidebar on desktop → accessible via hamburger drawer on mobile.
- **Chat input**: `max-w-4xl` centered on desktop → full-width with reduced padding on mobile. Bottom padding includes `env(safe-area-inset-bottom)` for notched devices.

## Animation System

### CSS Animations

| Name | Duration | Behavior | Use |
|------|----------|----------|-----|
| `glow-pulse` | 3s infinite | `box-shadow` oscillation, 15px → 30px blue | AI processing indicator on chat input |
| `shimmer` | 1.5s infinite | Horizontal translate sweep | Loading skeleton placeholders |
| `cursor-blink` | 1s step-end | Opacity toggle (1 → 0) | Streaming text cursor |
| `streaming-fade-in` | 0.15–0.3s ease-out | Opacity fade | Streaming content appearance |

### Framer Motion Animations

- **Modals**: `spring`, stiffness 200–300, damping 25. Scale 0.95 → 1, opacity 0 → 1.
- **Overlay panels**: `spring`, stiffness 200, damping 25. Slide from right (`x: "100%" → 0`).
- **Dropdown menus**: `ease-out`, 0.2s. Scale 0.95 → 1, y: -10 → 0, opacity 0 → 1.
- **Mobile sidebar sheet**: `spring`, stiffness 300, damping 30. Slide from left.

### Transition Utilities

- **Color transitions**: `transition-colors duration-300` on `<body>` for theme switching.
- **Button transitions**: `transition-colors` (default 150ms) on all interactive elements.
- **No page transitions**: The SPA routes are all overlay-based; there are no full-page route transitions.

## Icons

**Library**: Lucide React (`lucide-react` v0.576+). Consistent 1.5–2px stroke width, 16–24px sizing. All icons use the `currentColor` pattern — color is controlled via Tailwind text classes.

**Icon sizing**: 16px in compact UI (nav items, menu entries), 18–20px in headers and buttons, 24px in welcome screen.

**Icon color semantics**:
- `text-neutral-400` / `text-neutral-500`: Default UI chrome
- `text-blue-500`: AI/chat actions, skill center
- `text-purple-500`: Data center, admin functions
- `text-emerald-500`: Learning center, success
- `text-amber-400`: Sun/light mode indicator
- `text-rose-400`: Destructive actions
- `text-violet-500`: Deep think toggle
- `text-yellow-500`: Credits/balance
- `text-white`: Active nav items on colored backgrounds

## Do's and Don'ts

### Do
- Use `rounded-full` for all action-triggering elements — buttons, tag pills, mode switchers, badges. The capsule IS the interactive shape signal.
- Apply semantic color accents (blue/purple/emerald/amber/rose) to tag functional domains consistently. Blue = AI, purple = data, emerald = learning, amber = status, rose = danger.
- Set sidebar nav active states as full-color fills (`bg-purple-600`, `bg-blue-600`, `bg-emerald-600`) with optional glow shadows.
- Use `shadow-2xl` for all modals and overlay panels — this is the system's "floating above canvas" depth level.
- Animate modal/panel entry with Framer Motion spring (stiffness 200, damping 25).
- Apply the `transition-colors` class to all interactive elements for smooth hover/active state changes.
- Use Geist Mono for all code — inline, blocks, file paths — at 14px with 1.6 leading.
- Keep dark mode as the primary design target; light mode is supported but secondary.
- Enforce 44px minimum touch targets on mobile via the `.compact` class opt-out pattern.

### Don't
- Don't introduce a sixth semantic accent color; the five-domain system (blue/purple/emerald/amber/rose) is closed.
- Don't use CSS gradients for decorative backgrounds — use the grid pattern, glow animations, or flat colors.
- Don't add backdrop-blur or frosted glass effects — all panels use opaque `neutral-950` backgrounds.
- Don't use `transform: scale()` for button press states — rely on color shifts (`transition-colors`) instead.
- Don't mix font families — Geist Sans for UI, Geist Mono for code, no exceptions.
- Don't use weight 300 or 800 — the weight ladder is 400 / 500 / 600 / 700.
- Don't apply uppercase outside of table headers (13px / 600 / 0.05em tracking / uppercase).
- Don't use `rounded-full` for containers (cards, modals, panels) — the capsule signals an action, not a surface.
- Don't add borders thicker than 1px — the system uses thin hairlines exclusively.

## Responsive Behavior Details

### Image Behavior
- Product images and thumbnails use `rounded-lg` (8px) or `rounded-md` (6px).
- No full-bleed imagery — all images sit inside containers with padding.
- Lazy loading via Next.js `next/image` with WebP format and responsive `srcset`.

### Form Behavior
- Form validation and error states use red border + red text message pattern.
- Required field indicators: red asterisk.
- Disabled inputs: reduced opacity (50%), no interaction.

## State Management

The UI state is managed via Zustand v5 with `persist` middleware (localStorage key: `autonome-ui-storage`) and `immer` for immutable updates.

| Store | Persisted | Purpose |
|-------|-----------|---------|
| `useUIStore` | theme, autoExecuteStrategy, globalTaskMode | UI chrome state |
| `useWorkspaceStore` | No | Current project, session, file attachments |
| `useChatStore` | No | Messages, tags, mirror states |
| `useAuthStore` | No (token in cookie) | Auth token, user profile, credits |
| `useClaudeStore` | No | Claude mode state |
| `useForgeStore` | No | Skill forge state |
| `useTaskStore` | No | Task center state |
| `useLearningStore` | No | Learning center state |

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Framework | Next.js 16 (App Router) |
| UI Library | React 19 |
| Styling | Tailwind CSS v4 + `tw-animate-css` + `@tailwindcss/typography` |
| Component Primitives | shadcn/ui (New York style, slate base) |
| Icons | Lucide React v0.576 |
| Animations | Framer Motion + CSS keyframes |
| State | Zustand v5 + Immer + Persist |
| Toast | Sonner |
| AI SDK | Vercel AI SDK (`@ai-sdk/react`, `ai`) |
| Markdown | react-markdown + remark-gfm + rehype-katex |
| Code Highlighting | react-syntax-highlighter |
| Virtualization | @tanstack/react-virtual |
| Charts | ECharts (interactive plots) |
| DAG Visualization | ReactFlow |
| Code Editor | Monaco Editor (`@monaco-editor/react`) |
| Terminal | xterm.js (`@xterm/xterm` + `@xterm/addon-fit`) |
| Classname Utils | clsx + tailwind-merge → `cn()` |

## Iteration Guide

1. Reference components by their semantic name (`button-primary`, `sidebar`, `overlay-panel`).
2. Always use `rounded-full` for actions, `rounded-lg`/`rounded-xl` for containers.
3. Apply exactly one semantic accent color per functional domain — never mix blue + purple on the same element.
4. Use Tailwind utility classes directly — there is no centralized component library or design token indirection beyond the CSS custom properties.
5. Dark mode is the default; always design for dark first, then verify light mode.
6. Animate modals and panels with Framer Motion spring (stiffness 200, damping 25).
7. Code blocks: 14px Geist Mono, 1.6 leading, 0.75em radius, `bg-neutral-800`.
8. Touch targets on mobile: 44px minimum via the `.compact` opt-out pattern.

## Known Gaps

- **No centralized design token system**: Semantic colors (blue/purple/emerald) are applied as raw Tailwind classes rather than as named design tokens. There is no single source of truth for "what is the primary blue?"
- **No shared Button component**: Every button is styled inline with Tailwind classes. Different parts of the app have slightly different button implementations (padding variations, shadow differences).
- **No theming beyond light/dark**: The OKLCH variable system supports only two modes. There is no high-contrast mode, no colorblind mode, no custom theme builder.
- **Form validation states** are not systematically documented or tokenized — they exist as ad-hoc Tailwind class combinations.
- **Empty states and error states** vary between components — there is no shared EmptyState or ErrorState component.
- **The scrollbar styling** assumes a dark background (`rgba(255, 255, 255, ...)` thumb colors) and does not adapt for light mode.
- **No loading skeleton system** beyond the `shimmer` CSS animation — skeleton shapes are built ad-hoc per component.
- **Overlay panel widths** are inconsistent: Data Center is 900px fixed, Control Panel is 1200px max, all others are 85vw / 1152px max. There is no shared panel size token.
- **Mobile bottom nav** has no labels — relies on icon recognition alone, which may not be sufficient for all users.
- **The grid-pattern background** is the only texture element and is not formalized as a design token.
