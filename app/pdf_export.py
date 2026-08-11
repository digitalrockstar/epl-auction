"""PDF exports (item 6). Uses reportlab with bundled DejaVu fonts so the
₹ symbol renders correctly regardless of what fonts the host machine has."""
import io
import os
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak

FONT_DIR = os.path.join(os.path.dirname(__file__), "static", "fonts")
pdfmetrics.registerFont(TTFont("DejaVu", os.path.join(FONT_DIR, "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont("DejaVu-Bold", os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")))

GOLD = colors.HexColor("#c98f1f")
DARK = colors.HexColor("#14161d")
BORDER = colors.HexColor("#cccccc")

styles = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=styles["Heading1"], fontName="DejaVu-Bold", textColor=GOLD, fontSize=20)
H2 = ParagraphStyle("H2", parent=styles["Heading2"], fontName="DejaVu-Bold", textColor=DARK, fontSize=14, spaceBefore=14)
BODY = ParagraphStyle("Body", parent=styles["Normal"], fontName="DejaVu", fontSize=10)
MUTED = ParagraphStyle("Muted", parent=styles["Normal"], fontName="DejaVu", fontSize=9, textColor=colors.grey)


def _inr(n):
    if n is None:
        return "-"
    from app.templating import inr as _grouped
    return "\u20b9" + _grouped(n)


def _table(rows, col_widths, header_bg=GOLD):
    t = Table(rows, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "DejaVu"),
        ("FONTNAME", (0, 0), (-1, 0), "DejaVu-Bold"),
        ("BACKGROUND", (0, 0), (-1, 0), header_bg),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f7f7")]),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def _doc(buf, title):
    return SimpleDocTemplate(buf, pagesize=A4, title=title, topMargin=18 * mm, bottomMargin=15 * mm,
                              leftMargin=15 * mm, rightMargin=15 * mm)


def team_rosters_pdf(teams) -> bytes:
    """One page per team: squad, prices, purse summary."""
    buf = io.BytesIO()
    doc = _doc(buf, "EPL Season 3 - Team Rosters")
    story = []
    for i, team in enumerate(teams):
        story.append(Paragraph(f"{team.name}", H1))
        story.append(Paragraph(
            f"Manager: {team.manager.name if team.manager else '-'} &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"Purse spent: {_inr(team.purse_spent)} of {_inr(team.purse_total)} "
            f"&nbsp;&nbsp;|&nbsp;&nbsp; Remaining: {_inr(team.purse_remaining)}", MUTED))
        story.append(Spacer(1, 10))
        rows = [["#", "Player", "Skill", "Captain", "Price"]]
        for n, p in enumerate(team.players, start=1):
            rows.append([str(n), p.user.name if p.user else "-", p.primary_skill or "-",
                         "Yes" if p.is_captain else "", _inr(p.sold_price)])
        if len(rows) == 1:
            rows.append(["-", "No players bought yet", "-", "-", "-"])
        story.append(_table(rows, [20 * mm, 55 * mm, 35 * mm, 25 * mm, 30 * mm]))
        if i < len(teams) - 1:
            story.append(PageBreak())
    doc.build(story)
    return buf.getvalue()


def auction_summary_pdf(sold, unsold) -> bytes:
    """Every sold and unsold player across both auctions."""
    buf = io.BytesIO()
    doc = _doc(buf, "EPL Season 3 - Auction Summary")
    story = [Paragraph("Auction Summary", H1), Spacer(1, 6)]

    story.append(Paragraph(f"Sold ({len(sold)})", H2))
    rows = [["Player", "Skill", "Team", "Price", "Type"]]
    for a in sold:
        rows.append([a.player.user.name if a.player and a.player.user else "-", a.player.primary_skill or "-",
                     a.current_team.name if a.current_team else "-", _inr(a.current_bid),
                     "Captain" if a.auction_type.value == "captain" else "Player"])
    if len(rows) == 1:
        rows.append(["-", "-", "-", "-", "-"])
    story.append(_table(rows, [45 * mm, 35 * mm, 40 * mm, 30 * mm, 20 * mm]))

    story.append(Paragraph(f"Unsold ({len(unsold)})", H2))
    rows = [["Player", "Skill", "Type"]]
    for a in unsold:
        rows.append([a.player.user.name if a.player and a.player.user else "-", a.player.primary_skill or "-",
                     "Captain" if a.auction_type.value == "captain" else "Player"])
    if len(rows) == 1:
        rows.append(["-", "-", "-"])
    story.append(_table(rows, [70 * mm, 60 * mm, 40 * mm]))

    doc.build(story)
    return buf.getvalue()


def points_schedule_pdf(matches, standings) -> bytes:
    """Points table + full match schedule with results where played."""
    buf = io.BytesIO()
    doc = _doc(buf, "EPL Season 3 - Points & Schedule")
    story = [Paragraph("Points Table", H1), Spacer(1, 6)]
    rows = [["Team", "Played", "Won", "Lost", "Points"]]
    for s in standings:
        rows.append([s["name"], str(s["played"]), str(s["won"]), str(s["lost"]), str(s["points"])])
    story.append(_table(rows, [60 * mm, 30 * mm, 30 * mm, 30 * mm, 30 * mm]))

    story.append(Paragraph("Schedule", H2))
    rows = [["#", "Type", "Date", "Teams", "Result"]]
    for m in matches:
        result = "-"
        if m.winner_team_id:
            winner = m.team_a if m.winner_team_id == m.team_a_id else m.team_b
            result = f"{winner.name} won" if winner else "-"
        rows.append([str(m.match_number), m.match_type.title(), m.match_date.strftime("%d %b, %I:%M %p"),
                     f"{m.team_a.name} vs {m.team_b.name}", result])
    story.append(_table(rows, [15 * mm, 25 * mm, 35 * mm, 55 * mm, 35 * mm]))
    doc.build(story)
    return buf.getvalue()


def player_detail_pdf(player) -> bytes:
    buf = io.BytesIO()
    doc = _doc(buf, f"EPL Season 3 - {player.user.name if player.user else 'Player'}")
    story = [Paragraph(player.user.name if player.user else "-", H1)]
    rows = [
        ["Skill", player.primary_skill or "-"],
        ["Batting", f"{player.batting_position or '-'} / {player.batting_hand or '-'}"],
        ["Bowling", f"{player.bowling_style or '-'} / {player.bowling_hand or '-'}"],
        ["Wicketkeeper", player.is_wicketkeeper or "-"],
        ["Experience", player.experience_level or "-"],
        ["Wants captaincy", "Yes" if player.wants_captaincy else "No"],
        ["Team", player.team.name if player.team else "Unsold / not yet auctioned"],
        ["Sold price", _inr(player.sold_price) if player.sold_price else "-"],
        ["Fee status", player.fee_status.value.title() if player.fee_status else "-"],
    ]
    story.append(_table(rows, [45 * mm, 100 * mm], header_bg=DARK))
    if player.brief:
        story.append(Paragraph("About", H2))
        story.append(Paragraph(player.brief, BODY))
    doc.build(story)
    return buf.getvalue()
