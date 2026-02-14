#!/usr/bin/env python3
"""Render terminal-style frames for the demo video.

Sprint 45: Rewritten to highlight the HIRING FLOW as the centerpiece:
  Task Submission → Marketplace Search → Skill Matching → x402 Payment → Completion
"""
from PIL import Image, ImageDraw, ImageFont
import os

W, H = 1920, 1080
BG = (13, 17, 23)  # GitHub dark background
FG = (230, 237, 243)
GREEN = (34, 197, 94)
CYAN = (34, 211, 238)
YELLOW = (234, 179, 8)
BLUE = (96, 165, 250)
MAGENTA = (192, 132, 252)
GRAY = (148, 163, 184)
DIM = (100, 116, 139)
WHITE = (255, 255, 255)

# Use a monospace font
try:
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 16)
    font_bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 16)
    font_title = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 14)
    font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 18)
except Exception:
    font = ImageFont.load_default()
    font_bold = font
    font_title = font
    font_large = font

LINE_HEIGHT = 22
MARGIN_X = 40
MARGIN_Y = 50

def draw_title_bar(draw):
    """Draw terminal title bar."""
    draw.rectangle([(0, 0), (W, 36)], fill=(30, 30, 30))
    # Traffic light buttons
    draw.ellipse([(16, 12), (28, 24)], fill=(255, 95, 86))
    draw.ellipse([(36, 12), (48, 24)], fill=(255, 189, 46))
    draw.ellipse([(56, 12), (68, 24)], fill=(39, 201, 63))
    draw.text((W//2 - 120, 10), "HireWire — Agent Hiring Pipeline", fill=GRAY, font=font_title)

def draw_line(draw, y, segments):
    """Draw a line of text with color segments: [(text, color), ...]"""
    x = MARGIN_X
    for text, color in segments:
        draw.text((x, y), text, fill=color, font=font)
        x += len(text) * 9.6  # approximate char width

def create_frame(lines, filename):
    """Create a frame image with colored terminal lines."""
    img = Image.new('RGB', (W, H), BG)
    draw = ImageDraw.Draw(img)
    draw_title_bar(draw)

    y = MARGIN_Y
    for line in lines:
        if isinstance(line, str):
            draw.text((MARGIN_X, y), line, fill=FG, font=font)
        else:
            draw_line(draw, y, line)
        y += LINE_HEIGHT

    img.save(filename)

output_dir = "/home/agent/projects/hirewire/docs/demo/video-assets/frames"
os.makedirs(output_dir, exist_ok=True)

# ── Frame 1: Task Submission ──────────────────────────────────────────────
# The user submits a task → CEO agent receives and analyzes it
frame1_lines = [
    [("$ ", GREEN), ("hirewire submit --task 'Analyze competitor pricing across top 5 AI platforms'", FG)],
    "",
    [("╔══════════════════════════════════════════════════════════════════╗", CYAN)],
    [("║   HireWire — Where AI Agents Hire AI Agents                    ║", CYAN)],
    [("║   Microsoft AI Dev Days 2026  ·  1,540 tests  ·  Live on Azure ║", CYAN)],
    [("╚══════════════════════════════════════════════════════════════════╝", CYAN)],
    "",
    [("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", DIM)],
    [("Step [1/5]  ", YELLOW), ("TASK SUBMISSION", WHITE)],
    [("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", DIM)],
    "",
    [("  ► ", BLUE), ("Task received by CEO Agent (Azure GPT-4o)", FG)],
    [("    ", FG), ("Task: ", GRAY), ("\"Analyze competitor pricing across top 5 AI platforms\"", CYAN)],
    "",
    [("  ► ", BLUE), ("CEO analyzing task requirements...", FG)],
    [("    ", FG), ("Type:       ", GRAY), ("research + analysis", CYAN)],
    [("    ", FG), ("Complexity: ", GRAY), ("high", YELLOW), (" (multi-source data + synthesis)", DIM)],
    [("    ", FG), ("Skills needed:", GRAY)],
    [("    ", FG), ("  • ", DIM), ("competitive_analysis", CYAN), (" (primary)", DIM)],
    [("    ", FG), ("  • ", DIM), ("financial_modeling", CYAN), (" (secondary)", DIM)],
    [("    ", FG), ("  • ", DIM), ("web_search", CYAN), (" (supporting)", DIM)],
    "",
    [("  ✓ ", GREEN), ("Task decomposed", FG), (" — searching marketplace for best agents...", GRAY)],
    "",
    [("  ████░░░░░░░░░░░░░░░░░░░░  ", GREEN), ("1/5", FG)],
]
create_frame(frame1_lines, f"{output_dir}/frame_01.png")

# ── Frame 2: Agent Marketplace Search ─────────────────────────────────────
# CEO queries the marketplace, skill matching finds candidates
frame2_lines = [
    [("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", DIM)],
    [("Step [2/5]  ", YELLOW), ("AGENT MARKETPLACE SEARCH", WHITE)],
    [("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", DIM)],
    "",
    [("  ► ", BLUE), ("Querying Agent Marketplace via MCP Registry...", FG)],
    [("    ", FG), ("GET /marketplace/agents?skills=competitive_analysis,financial_modeling", DIM)],
    "",
    [("  ┌──────────────────────────────────────────────────────────────┐", CYAN)],
    [("  │ ", CYAN), ("MARKETPLACE RESULTS                    5 agents found  ", FG), ("│", CYAN)],
    [("  ├──────────────────────────────────────────────────────────────┤", CYAN)],
    [("  │  ", CYAN), ("Agent             Skills              Price    Match ", FG), ("│", CYAN)],
    [("  ├──────────────────────────────────────────────────────────────┤", CYAN)],
    [("  │  ", CYAN), ("Research     ", GREEN), ("  analysis,search       ", FG), ("free   ", GREEN), ("  87%  ", YELLOW), ("│", CYAN)],
    [("  │  ", CYAN), ("analyst-ext  ", MAGENTA), ("  competitive,finance   ", FG), ("$0.50  ", GREEN), ("  95%  ", GREEN), ("│", CYAN)],
    [("  │  ", CYAN), ("Builder      ", GREEN), ("  code,testing          ", FG), ("free   ", GREEN), ("  32%  ", DIM), ("│", CYAN)],
    [("  │  ", CYAN), ("data-ext     ", MAGENTA), ("  scraping,analysis     ", FG), ("$0.25  ", GREEN), ("  78%  ", YELLOW), ("│", CYAN)],
    [("  │  ", CYAN), ("CEO          ", GREEN), ("  routing,budgeting     ", FG), ("free   ", GREEN), ("  15%  ", DIM), ("│", CYAN)],
    [("  └──────────────────────────────────────────────────────────────┘", CYAN)],
    "",
    [("  ► ", BLUE), ("Skill matching algorithm:", FG)],
    [("    ", FG), ("1. Cosine similarity on skill vectors", DIM)],
    [("    ", FG), ("2. Reputation-weighted scoring (Thompson sampling)", DIM)],
    [("    ", FG), ("3. Budget-aware ranking", DIM)],
    "",
    [("  ✓ ", GREEN), ("Top match: ", FG), ("analyst-ext-001", CYAN), (" (95% skill match, $0.50/call)", GRAY)],
    [("  ✓ ", GREEN), ("Runner-up:  ", FG), ("Research", CYAN), (" (87% match, internal — free)", GRAY)],
    "",
    [("  █████████░░░░░░░░░░░░░░░  ", GREEN), ("2/5", FG)],
]
create_frame(frame2_lines, f"{output_dir}/frame_02.png")

# ── Frame 3: Hiring Decision + x402 USDC Payment ─────────────────────────
# CEO selects agents, escrow budget, x402 payment proof signed
frame3_lines = [
    [("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", DIM)],
    [("Step [3/5]  ", YELLOW), ("HIRING + x402 USDC PAYMENT", WHITE)],
    [("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", DIM)],
    "",
    [("  ► ", BLUE), ("CEO hiring 2 agents for this task:", FG)],
    [("    ", FG), ("1. ", GRAY), ("analyst-ext-001", CYAN), (" — external agent (x402 paid)", MAGENTA)],
    [("    ", FG), ("2. ", GRAY), ("Research", CYAN), (" — internal agent (free)", GREEN)],
    "",
    [("  ► ", BLUE), ("Budget allocation:", FG)],
    [("    ", FG), ("Total budget:       ", GRAY), ("$5.00 USDC", GREEN)],
    [("    ", FG), ("Escrowed for x402:  ", GRAY), ("$0.50 USDC", YELLOW)],
    "",
    [("  ┌─────────────────────────────────────────────────────────────┐", MAGENTA)],
    [("  │ ", MAGENTA), ("x402 PAYMENT PROTOCOL                                     ", FG), ("│", MAGENTA)],
    [("  │                                                             │", MAGENTA)],
    [("  │  ", MAGENTA), ("1. CEO creates EIP-712 signed payment proof           ", GRAY), ("  │", MAGENTA)],
    [("  │     ", MAGENTA), ("Amount: $0.50 USDC  Chain: Base  Nonce: 47         ", GREEN), ("│", MAGENTA)],
    [("  │  ", MAGENTA), ("2. HTTP 402 → Payment Required from analyst-ext-001  ", GRAY), ("  │", MAGENTA)],
    [("  │  ", MAGENTA), ("3. CEO sends signed proof in X-PAYMENT header        ", GRAY), ("  │", MAGENTA)],
    [("  │  ", MAGENTA), ("4. Agent verifies proof → accepts task                ", GRAY), ("  │", MAGENTA)],
    [("  │  ", MAGENTA), ("5. Escrow held until task completion                  ", GRAY), ("  │", MAGENTA)],
    [("  │                                                             │", MAGENTA)],
    [("  └─────────────────────────────────────────────────────────────┘", MAGENTA)],
    "",
    [("  ✓ ", GREEN), ("analyst-ext-001 hired via x402", FG), (" — $0.50 USDC escrowed", YELLOW)],
    [("  ✓ ", GREEN), ("Research agent assigned (internal)", FG)],
    [("  ✓ ", GREEN), ("HITL gate: ", FG), ("auto-approved", GREEN), (" (under $5 threshold)", DIM)],
    "",
    [("  ██████████████░░░░░░░░░░  ", GREEN), ("3/5", FG)],
]
create_frame(frame3_lines, f"{output_dir}/frame_03.png")

# ── Frame 4: Task Execution by Agents ─────────────────────────────────────
# Agents execute in parallel, GPT-4o powers the work
frame4_lines = [
    [("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", DIM)],
    [("Step [4/5]  ", YELLOW), ("TASK EXECUTION (GPT-4o)", WHITE)],
    [("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", DIM)],
    "",
    [("  ► ", BLUE), ("Running 2 agents concurrently via Agent Framework...", FG)],
    "",
    [("  ┌─ analyst-ext-001 (x402) ──────────────── ", MAGENTA), ("done ✓", GREEN), (" ─┐", CYAN)],
    [("  │  ", CYAN), ("Task: Competitive pricing analysis                     ", FG), ("│", CYAN)],
    [("  │  ", CYAN), ("Model: GPT-4o (Azure OpenAI)                           ", FG), ("│", CYAN)],
    [("  │  ", CYAN), ("Output: 5 platforms compared, pricing tiers mapped     ", FG), ("│", CYAN)],
    [("  │  ", CYAN), ("Tokens: 2,847 input / 1,523 output                    ", DIM), ("│", CYAN)],
    [("  │  ", CYAN), ("Time: 3.2s  Cost: ", FG), ("$0.50 USDC", GREEN), ("                           ", FG), ("│", CYAN)],
    [("  └────────────────────────────────────────────────────────┘", CYAN)],
    "",
    [("  ┌─ Research (internal) ─────────────────── ", GREEN), ("done ✓", GREEN), (" ─┐", CYAN)],
    [("  │  ", CYAN), ("Task: Market data gathering & report writing           ", FG), ("│", CYAN)],
    [("  │  ", CYAN), ("Model: GPT-4o (Azure OpenAI)                           ", FG), ("│", CYAN)],
    [("  │  ", CYAN), ("Output: Detailed market report with recommendations   ", FG), ("│", CYAN)],
    [("  │  ", CYAN), ("Tokens: 1,892 input / 2,104 output                    ", DIM), ("│", CYAN)],
    [("  │  ", CYAN), ("Time: 2.8s  Cost: ", FG), ("free (internal)", GREEN), ("                      ", FG), ("│", CYAN)],
    [("  └────────────────────────────────────────────────────────┘", CYAN)],
    "",
    [("  ✓ ", GREEN), ("Both agents completed", FG), (" — ", DIM), ("3.2s total (parallel)", GRAY)],
    [("  ✓ ", GREEN), ("CEO aggregating results with GPT-4o...", FG)],
    "",
    [("  ████████████████████░░░░  ", GREEN), ("4/5", FG)],
]
create_frame(frame4_lines, f"{output_dir}/frame_04.png")

# ── Frame 5: Task Completion + Payment Settlement ─────────────────────────
# Final results, payment released from escrow, ledger updated
frame5_lines = [
    [("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", DIM)],
    [("Step [5/5]  ", YELLOW), ("TASK COMPLETE — PAYMENT SETTLED", WHITE)],
    [("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", DIM)],
    "",
    [("  ┌──────────────────────────────────────────────────────────────┐", GREEN)],
    [("  │ ", GREEN), ("PAYMENT LEDGER                                            ", FG), ("│", GREEN)],
    [("  ├──────────────────────────────────────────────────────────────┤", GREEN)],
    [("  │  ", GREEN), ("Agent              Amount       Type           Status  ", FG), ("│", GREEN)],
    [("  ├──────────────────────────────────────────────────────────────┤", GREEN)],
    [("  │  ", GREEN), ("analyst-ext-001    $0.50 USDC  ", FG), ("x402 (Base)    ", MAGENTA), ("settled ", GREEN), ("│", GREEN)],
    [("  │  ", GREEN), ("Research           $0.00        ", FG), ("internal       ", CYAN), ("done    ", GREEN), ("│", GREEN)],
    [("  ├──────────────────────────────────────────────────────────────┤", GREEN)],
    [("  │  ", GREEN), ("Total: ", FG), ("$0.50 USDC", YELLOW), ("    External (x402): ", FG), ("$0.50 USDC", MAGENTA), ("       │", GREEN)],
    [("  │  ", GREEN), ("Escrow released: ", FG), ("$0.50 USDC", GREEN), ("  Remaining budget: ", FG), ("$4.50    ", GREEN), ("│", GREEN)],
    [("  └──────────────────────────────────────────────────────────────┘", GREEN)],
    "",
    [("  ✓ ", GREEN), ("Task completed: ", FG), ("Competitor pricing analysis delivered", CYAN)],
    [("  ✓ ", GREEN), ("x402 escrow released to analyst-ext-001", FG)],
    [("  ✓ ", GREEN), ("Learning system updated: ", FG), ("analyst-ext-001 reputation +0.12", CYAN)],
    [("  ✓ ", GREEN), ("Responsible AI: ", FG), ("all checks passed", GREEN), (" (bias: clean, PII: clean)", DIM)],
    "",
    [("  █████████████████████████  ", GREEN), ("5/5 ✓ Complete", GREEN)],
    "",
    [("╔══════════════════════════════════════════════════════════════════╗", CYAN)],
    [("║  HIRING FLOW COMPLETE                                          ║", CYAN)],
    [("║  Task → Marketplace → Skill Match → x402 Payment → Delivered  ║", CYAN)],
    [("║                                                                ║", CYAN)],
    [("║  Azure GPT-4o ✓  Cosmos DB ✓  x402 ✓  1,540 tests ✓          ║", CYAN)],
    [("╚══════════════════════════════════════════════════════════════════╝", CYAN)],
]
create_frame(frame5_lines, f"{output_dir}/frame_05.png")

print(f"Created 5 terminal frames in {output_dir}")
print("Hiring flow: Task Submission → Marketplace Search → Skill Matching + x402 → Execution → Settlement")
