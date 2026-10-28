import csv
import io
from xml.sax.saxutils import escape


def report_rows(run):
    rows = []
    for i, check in enumerate(run['checks'], 1):
        for c in check['rows']:
            rows.append([f'Precheck {i}', check['timestamp'], check['position'], c['terminal_a'], c['terminal_b'], c['probe'], c['input'], c['expected'], c['actual'], 'PASS' if c['pass'] else 'FAIL'])
    for i, step in enumerate(run['steps'], 1):
        for c in step['contacts']['rows']:
            rows.append([f'{i} {step["command"]}', step['timestamp'], step['expected_position'], c['terminal_a'], c['terminal_b'], c['probe'], c['input'], c['expected'], c['actual'], 'PASS' if c['pass'] else 'FAIL'])
    return rows


def csv_report(run):
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    def safe(value):
        text = str(value)
        return "'" + text if text.startswith(('=', '+', '-', '@', '\t', '\r')) else text
    writer.writerow(['SIMULATION - college project, no physical PLC operation'])
    for key, val in [('Run', run['id']), ('Operator', run['operator']), ('Status', run['status']), ('Reason', run['reason']), ('Breaker', run['profile']['breaker']), ('Drawing revision', run['profile']['drawing_revision']), ('Profile revision', run['profile']['revision']), ('Profile SHA256', run['profile']['digest'])]:
        writer.writerow([key, safe(val)])
    writer.writerow(['Stage', 'UTC timestamp', 'Expected position', 'TB A', 'TB B', 'Probe', 'PLC input', 'Expected', 'Actual', 'Result'])
    for row in report_rows(run):
        writer.writerow([safe(v) for v in row])
    if run.get('functional_approval'):
        writer.writerow(['Functional tests approved by', safe(run['functional_approval']['operator']), 'Contact check reviewed (UTC)', run['functional_approval']['check_timestamp']])
    writer.writerow(['Developed by Prashil Dalvi and Team Trishul', 'Amruthvahini College of Engg', 'ABB - independent college project'])
    return stream.getvalue()


def pdf_report(run):
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    out = io.BytesIO()
    doc = SimpleDocTemplate(out, pagesize=A4, topMargin=64, bottomMargin=65)
    styles = getSampleStyleSheet()
    def p(text, style='BodyText'):
        return Paragraph(escape(str(text)), styles[style])
    items = [p('Breaker functional test report', 'Title'), p('SIMULATION ONLY - no physical breaker tested', 'Heading2')]
    profile = run['profile']
    for label, value in [('Run', run['id']), ('Breaker', profile['breaker']), ('Drawing revision', profile['drawing_revision']), ('Profile revision', profile['revision']), ('Operator', run['operator']), ('Approved by', profile['approved_by']), ('Started (UTC)', run['started']), ('Finished (UTC)', run['finished']), ('Result', run['status']), ('Notes', run['reason']), ('Profile SHA256', profile['digest'])]:
        items.append(p(f'{label}: {value}'))
    items += [Spacer(1, 12), p('Functional sequence', 'Heading2')]
    if run.get('functional_approval'):
        approval = run['functional_approval']
        items.append(p(f'Functional tests approved by {approval["operator"]}; contact check reviewed (UTC): {approval["check_timestamp"]}'))
    for step in run['steps']:
        items.append(p(f'{step["command"]}: {"PASS" if step["pass"] else "FAIL"} | expected {step["expected_position"]}, actual {step["actual_position"]}'))
    items += [p('Contact observations and retest history', 'Heading2')]
    data = [[p(t) for t in ['Stage / UTC', 'Position', 'TB pair', 'Probe / input', 'Exp / actual', 'Result']]]
    for row in report_rows(run):
        stage, timestamp, pos, a, b, probe, inp, exp, actual, result = row
        data.append([p(f'{stage}\n{timestamp}'), p(pos), p(f'{a} / {b}'), p(f'{probe} / {inp}'), p(f'{int(exp)} / {int(actual)}'), p(result)])
    table = Table(data, colWidths=[126, 58, 91, 60, 70, 46], repeatRows=1)
    table.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e8eef4')), ('GRID', (0, 0), (-1, -1), .3, colors.HexColor('#cbd5e1')), ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('TOPPADDING', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 7)]))
    items += [table, Spacer(1, 12), p('Functional trip-circuit operation only. Coil resistance, insulation, current signatures and precision timing are not measured.')]
    def page(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(colors.HexColor('#e5e9ed'))
        canvas.setFont('Helvetica-Bold', 38)
        canvas.drawRightString(540, 794, 'ABB')
        canvas.setFillColor(colors.HexColor('#475569'))
        canvas.setFont('Helvetica', 9)
        canvas.drawString(42, 42, 'Amruthvahini College of Engg | Independent college project')
        canvas.drawString(42, 29, 'Developed by Prashil Dalvi and Team Trishul')
        canvas.drawRightString(550, 29, f'{doc.page}')
        canvas.restoreState()
    doc.build(items, onFirstPage=page, onLaterPages=page)
    return out.getvalue()
