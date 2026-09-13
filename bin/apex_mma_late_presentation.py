"""Readable, source-bound presentation of an already captured MMA late report.

No hydration, predictions, database writes, issuance, email or network calls.
The website uses only the standard library; PDF support is imported on demand.
"""
from __future__ import annotations

import hashlib
import html
import json
from datetime import date, datetime, timezone
from pathlib import Path

NOT_AVAILABLE = 'Not available'
METRICS = (
    ('Significant strikes landed / min', 'slpm'),
    ('Significant strikes absorbed / min', 'sapm'),
    ('Striking accuracy', 'str_acc'),
    ('Striking defense', 'str_def'),
    ('Takedowns / 15 min', 'td_avg'),
    ('Takedown accuracy', 'td_acc'),
    ('Takedown defense', 'td_def'),
    ('Submission attempts / 15 min', 'sub_avg'),
)
DISCIPLINES = {
    'amateur-mma': 'Amateur MMA',
    'pro-submission-grappling': 'Submission grappling',
    'pro-boxing': 'Boxing', 'pro-kickboxing': 'Kickboxing',
    'pro-sanda': 'Sanda', 'pro-wrestling': 'Wrestling',
}

def esc(value):
    return html.escape(str(value), quote=True)

def value(raw, suffix=''):
    return NOT_AVAILABLE if raw is None or raw == '' else str(raw) + suffix

def time_label(raw):
    if not raw:
        return NOT_AVAILABLE
    parsed = datetime.fromisoformat(str(raw).replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('PROFILE_TIMEZONE_REQUIRED')
    return parsed.astimezone(timezone.utc).strftime('%b %d, %Y, %H:%M UTC')

def validate_report(report):
    if (report.get('artifact_type') != 'LATE_DATA_REPORT'
            or report.get('sport') != 'MMA'
            or report.get('label') != 'LATE DATA RECOVERY NOT PREGAME T3'
            or report.get('picks') != [] or report.get('positions') != []
            or report.get('picks_published') is not False
            or report.get('official_issuance') is not False
            or report.get('prediction_generation_count') != 0
            or report.get('model_fit_count') != 0):
        raise ValueError('FACTUAL_REPORT_ONLY')
    digest = hashlib.sha256(json.dumps(
        {k: v for k, v in report.items() if k != 'report_sha256'},
        sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()
    if digest != report.get('report_sha256'):
        raise ValueError('REPORT_HASH_MISMATCH')
    return report

def ordered_bouts(report):
    current, cancelled = [], []
    for bout in report['official_card']['bouts']:
        if (bout.get('roster_disposition') == 'CURRENT_ROSTER'
                and bout.get('source_status') != 'CANCELLED'):
            current.append(bout)
        elif (bout.get('roster_disposition') == 'EXCLUDED_CANCELLED'
                and bout.get('source_status') == 'CANCELLED'):
            cancelled.append(bout)
        else:
            raise ValueError('UNVERIFIED_ROSTER_DISPOSITION')
    if (len(current) != report['current_roster_bout_count']
            or len(cancelled) != report['excluded_bout_count']):
        raise ValueError('ROSTER_COUNT_MISMATCH')
    order = lambda b: b['official_display_order']
    return sorted(current, key=order), sorted(cancelled, key=order)

def fighter_view(participant, event_date):
    facts = participant.get('facts') or {}
    stats = facts.get('career_stats') or []
    def scope(name):
        matches = [s for s in stats if s.get('scope') == name]
        if len(matches) > 1:
            raise ValueError('AMBIGUOUS_PROFILE_SCOPE')
        return matches[0] if matches else {}
    pro, rates = scope('pro-mma'), scope('ufc-only')
    age = NOT_AVAILABLE
    if facts.get('dob'):
        born, event = date.fromisoformat(facts['dob']), date.fromisoformat(event_date)
        years = event.year - born.year - ((event.month, event.day) < (born.month, born.day))
        age = str(years) if years >= 0 else NOT_AVAILABLE
    rows = [
        ('Professional MMA record', value(pro.get('record'))),
        ('Additional profile record', value(rates.get('record'))),
        ('Age on event date', age),
        ('Height', value(facts.get('height_inches'), ' in')),
        ('Reach', value(facts.get('reach_inches'), ' in')),
        ('Listed weight', value(facts.get('weight_lbs'), ' lb')),
        ('Stance', value(facts.get('stance'))),
    ] + [(label, value(rates.get(key))) for label, key in METRICS]
    notes = []
    if pro.get('record') and rates.get('record') and pro['record'] != rates['record']:
        notes.append('The two captured record entries differ; neither has been substituted for the other.')
    extras = [DISCIPLINES.get(s.get('scope'), 'Other recorded discipline') + ': ' + str(s['record'])
              for s in stats if s.get('scope') not in ('pro-mma', 'ufc-only') and s.get('record')]
    if extras:
        notes.append('Other records — ' + '; '.join(extras) + '.')
    if not participant.get('apex_mma_fighter_id'):
        notes.append('Fighter identity has not been fully reconciled in the captured report.')
    if any(v == NOT_AVAILABLE for _, v in rows):
        notes.append('Unavailable measurements remain explicitly marked; no values have been estimated.')
    return {
        'name': participant.get('official_display_name') or participant['name'],
        'rows': rows, 'notes': notes,
        'capture': time_label(participant.get('source_captured_at_utc')),
    }

def bout_view(bout, event_date):
    participants = {p['participant_slot']: p for p in bout['participants']}
    if len(bout['participants']) != 2 or set(participants) != {'A', 'B'}:
        raise ValueError('TWO_ORDERED_FIGHTERS_REQUIRED')
    left, right = [fighter_view(participants[s], event_date) for s in ('A', 'B')]
    # Bind display columns to the named matchup, not array order.
    for slot, expected in (('A', bout['fighter_a']), ('B', bout['fighter_b'])):
        p = participants[slot]
        if expected not in (p.get('name'), p.get('official_display_name')):
            raise ValueError('FIGHTER_COLUMN_NAME_MISMATCH')
    notes = ['Listed weights are profile values, not official weigh-in results.']
    missing = set(bout.get('missing_signals') or [])
    if 'official_weigh_in' in missing:
        notes.append('Official weigh-in results were not captured.')
    if 'corner_assignments' in missing:
        notes.append('Corner assignments were not captured.')
    if 'current_elemental_feature_surface' in missing:
        notes.append('Some required modeling inputs were unavailable.')
    if 'canonical_bout_id' in missing:
        notes.append('The cancelled matchup was not fully reconciled in the event records.')
    return {'left': left, 'right': right, 'notes': notes,
            'rows': [(label, a, b) for (label, a), (_, b) in zip(left['rows'], right['rows'])]}

COMPARISON_CSS = '''
.mma-facts { padding: 20px 24px; border-top: 1px solid #303030; }
.mma-facts table { width:100%; border-collapse:collapse; table-layout:fixed; font-size:14px; line-height:1.5; }
.mma-facts th,.mma-facts td { padding:9px 8px; border-bottom:1px solid #303030; text-align:left; vertical-align:top; overflow-wrap:anywhere; }
.mma-facts th:first-child { width:40%; }
.mma-facts thead th { color:#fff; font-weight:700; }
.mma-facts tbody th { font-weight:400; color:#aaa; }
.mma-facts td { color:#eee; }
.mma-facts .mma-notes { margin-top:16px; font-size:13px; line-height:1.6; color:#aaa; }
.mma-facts .mma-notes p { margin:8px 0; }
.mma-report-intro { max-width:900px; margin:18px 0 28px; }
.mma-report-intro p { line-height:1.65; }
.mma-cancelled { margin-top:32px; }
@media(max-width:600px) { .mma-facts { padding:16px 10px; } .mma-facts table { font-size:12px; } .mma-facts th,.mma-facts td { padding:8px 5px; } }
'''

def comparison_html(bout, event_date):
    view = bout_view(bout, event_date)
    out = '<section class="mma-facts" aria-label="Captured fighter comparison"><div class="market-label">FIGHTER COMPARISON · CAPTURED FACTS</div>'
    out += '<table><caption class="sr-only">Captured fighter measurements and rates; no picks issued.</caption><thead><tr><th scope="col">MEASUREMENT</th>'
    out += ''.join('<th scope="col">' + esc(view[side]['name']) + '</th>' for side in ('left', 'right'))
    out += '</tr></thead><tbody>'
    for label, left, right in view['rows']:
        out += '<tr><th scope="row">' + esc(label) + '</th><td>' + esc(left) + '</td><td>' + esc(right) + '</td></tr>'
    out += '</tbody></table><div class="mma-notes">'
    for side in ('left', 'right'):
        fighter = view[side]
        out += '<p><strong>' + esc(fighter['name']) + '</strong> · Profile captured ' + esc(fighter['capture']) + '.</p>'
        out += ''.join('<p>' + esc(note) + '</p>' for note in fighter['notes'])
    out += '<p>' + esc(' '.join(view['notes'])) + '</p></div></section>'
    return out

def intro_paragraphs(report):
    return [
        'No picks were issued for this event. This is a late factual report, not a pre-event T3 report or a T2 picks package.',
        'Roster captured ' + time_label(report['source_captured_at_utc']) + '. Fighter profiles were captured separately at the times shown. These are saved facts, not a live update; they may include information recorded after the event cutoff.',
        'The professional MMA record and additional profile record are separate captured entries. Their coverage has not been reconciled. Rates come from the additional profile; a record discrepancy is disclosed beside that fighter.',
    ]

def email_body(report):
    validate_report(report)
    current, cancelled = ordered_bouts(report)
    body = '<style>' + COMPARISON_CSS + '</style><h1>' + esc(report['event_name']) + '</h1>'
    body += '<h2>Late factual report · No picks issued</h2>'
    body += ''.join('<p>' + esc(p) + '</p>' for p in intro_paragraphs(report))
    for group, bouts in (('EVENT ROSTER', current), ('CANCELLED PAIRINGS — EXCLUDED FROM EVENT ROSTER', cancelled)):
        body += '<h2>' + group + '</h2>'
        for bout in bouts:
            body += '<h3>' + esc(bout['fighter_a'] + ' vs ' + bout['fighter_b']) + '</h3>'
            body += comparison_html(bout, report['event_date'])
    return body

def render_pdf(report, path):
    """One readable comparison per page, with the current roster first."""
    validate_report(report)
    current, cancelled = ordered_bouts(report)
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    regular = Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
    bold = regular.with_name('DejaVuSans-Bold.ttf')
    if not regular.is_file() or not bold.is_file():
        raise RuntimeError('PDF_UNICODE_FONT_MISSING')
    pdfmetrics.registerFont(TTFont('APEXLate', str(regular)))
    pdfmetrics.registerFont(TTFont('APEXLateBold', str(bold)))
    pdfmetrics.registerFontFamily('APEXLate', normal='APEXLate', bold='APEXLateBold')
    styles = {
        'body': ParagraphStyle('body', fontName='APEXLate', fontSize=10, leading=15, textColor=colors.HexColor('#cccccc'), spaceAfter=10),
        'small': ParagraphStyle('small', fontName='APEXLate', fontSize=8.5, leading=12, textColor=colors.HexColor('#aaaaaa'), spaceAfter=8),
        'title': ParagraphStyle('title', fontName='APEXLateBold', fontSize=24, leading=30, textColor=colors.white, spaceAfter=16),
        'heading': ParagraphStyle('heading', fontName='APEXLateBold', fontSize=16, leading=22, textColor=colors.white, spaceAfter=12),
        'cell': ParagraphStyle('cell', fontName='APEXLate', fontSize=9, leading=12, textColor=colors.HexColor('#eeeeee')),
    }
    p = lambda text, style='body': Paragraph(esc(text), styles[style])
    story = [Spacer(1, 22), p('MMA / UFC', 'small'), p(report['event_name'], 'title'),
             p(date.fromisoformat(report['event_date']).strftime('%B %d, %Y'), 'heading'),
             p('LATE FACTUAL REPORT · NO PICKS ISSUED', 'heading')]
    story += [p(text) for text in intro_paragraphs(report)]
    story += [Spacer(1, 12), p(str(len(current)) + ' roster bouts · ' + str(len(cancelled)) + ' cancelled pairings', 'heading'),
              p('How to read the comparisons', 'heading'),
              p('Striking rates show significant strikes per minute. Takedown and submission rates show averages per 15 minutes. Accuracy and defense are the captured percentages. Listed weight is not an official weigh-in. Missing values remain marked as not available.'),
              p('This presentation uses the same captured report as the original delivery. It does not add forecasts, update historical facts, or certify a betting advantage.'),
              p('Source: cached UFCALENDAR profiles. Rate definitions: UFCStats.', 'small')]
    for label, bouts in (('EVENT ROSTER', current), ('CANCELLED PAIRINGS · EXCLUDED', cancelled)):
        for number, bout in enumerate(bouts, 1):
            view = bout_view(bout, report['event_date'])
            story += [PageBreak(), p(label + ' · ' + str(number).zfill(2), 'small'),
                      p(bout['fighter_a'] + ' vs ' + bout['fighter_b'], 'heading'),
                      p(value(bout.get('weight_class')) + ' · ' + value(bout.get('scheduled_rounds')) + ' scheduled rounds', 'small')]
            rows = [[p('MEASUREMENT', 'cell'), p(view['left']['name'], 'cell'), p(view['right']['name'], 'cell')]]
            rows += [[p(a, 'cell'), p(b, 'cell'), p(c, 'cell')] for a, b, c in view['rows']]
            table = Table(rows, colWidths=[222, 150, 150], repeatRows=1, hAlign='LEFT')
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#262626')),
                ('LINEBELOW', (0, 0), (-1, -1), 0.3, colors.HexColor('#383838')),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 8), ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ]))
            story += [table, Spacer(1, 12)]
            for side in ('left', 'right'):
                fighter = view[side]
                story.append(p(fighter['name'] + ' · Profile captured ' + fighter['capture'] + '.', 'small'))
                story += [p(note, 'small') for note in fighter['notes']]
            story.append(p(' '.join(view['notes']), 'small'))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name('.' + path.name + '.tmp')
    count = [0]
    def chrome(canvas, doc):
        count[0] = doc.page
        canvas.saveState()
        canvas.setFillColor(colors.HexColor('#080808'))
        canvas.rect(0, 0, 612, 792, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont('APEXLateBold', 18)
        canvas.drawString(45, 759, 'APEX')
        canvas.setFont('APEXLate', 8)
        canvas.drawRightString(567, 759, 'SPORTS FORECASTING')
        canvas.setStrokeColor(colors.HexColor('#444444'))
        canvas.line(45, 746, 567, 746)
        canvas.setFillColor(colors.HexColor('#aaaaaa'))
        canvas.setFont('APEXLate', 7)
        canvas.drawString(45, 25, 'LATE FACTUAL REPORT · NO PICKS ISSUED')
        canvas.drawRightString(567, 25, 'apexrigor.com · ' + str(doc.page))
        canvas.restoreState()
    doc = SimpleDocTemplate(str(temporary), pagesize=(612, 792), rightMargin=45, leftMargin=45,
                            topMargin=62, bottomMargin=44, title='APEX MMA — Late factual report',
                            author='APEX Sports Forecasting', subject='Captured report SHA-256: ' + report['report_sha256'])
    try:
        doc.build(story, onFirstPage=chrome, onLaterPages=chrome)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return count[0]
