"""Presentation only: colours, portrait cards and disclosures."""
from pathlib import Path
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap, QPainter, QColor, QPen
from PySide6.QtWidgets import (QLabel, QWidget, QFrame, QVBoxLayout, QHBoxLayout,
    QGridLayout, QPushButton, QToolButton, QComboBox, QCheckBox, QPlainTextEdit,
    QScrollArea, QSizePolicy)

ROOT = Path(__file__).resolve().parent
STYLE = '''
QWidget { background: #101c19; color: #eee6d3; font-family: "Segoe UI"; font-size: 13px; }
QLabel { background: transparent; }
QLabel#title { font-family: Georgia; font-size: 25px; font-weight: bold; color: #d9c18b; }
QLabel#eyebrow { color: #b8a578; font-size: 10px; font-weight: bold; letter-spacing: 2px; }
QLabel#heading { font-family: Georgia; font-size: 23px; font-weight: bold; }
QLabel#muted { color: #a6b5ac; font-size: 12px; }
QLabel#status { color: #c9d8c8; padding: 8px 0; }
QFrame#card { background: #192a24; border: 1px solid #344c40; border-radius: 9px; }
QFrame#featured { background: #1e3027; border: 1px solid #b39a60; border-radius: 9px; }
QFrame#current { background: #16251f; border: 1px solid #344c40; border-radius: 7px; }
QLabel#hero { font-family: Georgia; font-size: 24px; font-weight: bold; }
QLabel#metric { font-family: Georgia; font-size: 29px; font-weight: bold; color: #eee6d3; }
QLabel#rank { font-family: Georgia; font-size: 23px; color: #c6ac70; }
QPushButton, QComboBox { background: #20352b; border: 1px solid #4a6150; border-radius: 5px; padding: 8px 12px; }
QPushButton:hover, QComboBox:hover { background: #2b4435; border-color: #b39a60; }
QPushButton:pressed { background: #17271e; }
QPushButton:disabled { color: #748077; background: #192720; border-color: #31443a; }
QPushButton#quiet { background: transparent; border-color: #344c40; color: #b9c3b9; padding: 5px 10px; }
QPushButton:focus, QToolButton:focus, QComboBox:focus, QCheckBox:focus { border: 1px solid #ddc287; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView { background: #20352b; selection-background-color: #425942; color: #eee6d3; }
QCheckBox { spacing: 9px; background: transparent; }
QCheckBox::indicator { width: 18px; height: 18px; border: 1px solid #718570; border-radius: 4px; background: #15271e; }
QCheckBox::indicator:checked { background: #a9bb7b; border: 2px solid #d8d9a9; }
QToolButton { color: #bfcabf; border: none; background: transparent; padding: 5px 0; text-align: left; }
QToolButton:hover { color: #e0c78f; }
QPlainTextEdit, QListWidget, QLineEdit { background: #13211b; color: #c4d0c3; border: 1px solid #344c40; border-radius: 5px; padding: 6px; selection-background-color: #526449; }
QListWidget::item { padding: 5px; border-bottom: 1px solid #25392d; }
QListWidget::item:selected { background: #314a37; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: #101c19; width: 9px; }
QScrollBar::handle:vertical { background: #455c49; min-height: 25px; border-radius: 4px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QToolTip { background: #2b3d2c; color: #eee6d3; border: 1px solid #b39a60; }
'''


def label(text='', name=None, wrap=False):
    w = QLabel(text)
    w.setTextFormat(Qt.TextFormat.PlainText)
    if name: w.setObjectName(name)
    w.setWordWrap(wrap)
    return w


def display_name(hero):
    return 'Mo & Krill' if hero == 'mo_and_krill' else hero.replace('_', ' ').title()


class Emblem(QWidget):
    def __init__(self):
        super().__init__(); self.setFixedSize(44, 44)
    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor('#bca16b'), 1.2)); p.drawEllipse(7, 7, 30, 30)
        p.drawEllipse(15, 15, 14, 14)
        for angle in range(0, 360, 45):
            p.save(); p.translate(22, 22); p.rotate(angle); p.drawLine(0, -21, 0, -10); p.restore()
        p.end()


class Portrait(QLabel):
    def __init__(self, hero, width=58, height=78):
        super().__init__(); self.setFixedSize(width, height)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pix = QPixmap(str(ROOT / 'assets' / 'hero_portraits' / f'{hero}.png'))
        if pix.isNull():
            self.setText('◇'); self.setToolTip(f'Portrait unavailable: {display_name(hero)}')
        else:
            self.setPixmap(pix.scaled(width, height, Qt.AspectRatioMode.KeepAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation))
        self.setAccessibleName(display_name(hero) + ' portrait')


class Disclosure(QWidget):
    def __init__(self, title, content, opened=False):
        super().__init__()
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(4)
        self.button = QToolButton(); self.button.setText(title); self.button.setCheckable(True)
        self.button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.content = content
        self.button.toggled.connect(self.set_open)
        layout.addWidget(self.button); layout.addWidget(content)
        self.button.setChecked(opened); self.set_open(opened)
    def set_open(self, opened):
        self.content.setVisible(opened)
        self.button.setArrowType(Qt.ArrowType.DownArrow if opened else Qt.ArrowType.RightArrow)


class PickCard(QFrame):
    def __init__(self, row, position, mode, count, bonus, current, expanded=False):
        super().__init__(); self.hero = row['hero']
        self.setObjectName('featured' if position == 1 else 'card')
        outer = QVBoxLayout(self); outer.setContentsMargins(14, 8, 14, 8); outer.setSpacing(6)
        top = QHBoxLayout(); top.setSpacing(12)
        top.addWidget(label(f'{position:02}', 'rank'))
        top.addWidget(Portrait(self.hero, 49, 66))
        title = QVBoxLayout(); title.setSpacing(4)
        title.addWidget(label(('Stay on ' if self.hero == current else '') + display_name(self.hero), 'hero'))
        title.addWidget(label(f'Previous #1: {count}', 'muted'))
        top.addLayout(title, 1)
        metric = QVBoxLayout(); metric.setSpacing(0)
        is_opportunity = mode == 'Best Opportunity'
        value = row.get('opportunity_percentile') if is_opportunity else row['score']
        number = label(f'{value:.1f}' if is_opportunity else f'{value:.2f}', 'metric')
        number.setAlignment(Qt.AlignmentFlag.AlignRight)
        caption = label('Opportunity percentile' if is_opportunity else 'Score points', 'muted')
        caption.setAlignment(Qt.AlignmentFlag.AlignRight)
        metric.addWidget(number); metric.addWidget(caption); top.addLayout(metric)
        outer.addLayout(top)
        if mode == 'Competitive':
            outer.addWidget(label(f"{row['difference']:+.2f} score points vs staying", 'muted'))
        if bonus is not None and bonus > 0:
            unit = 'percentile points' if is_opportunity else 'score points'
            outer.addWidget(label(f'Balance preference: +{bonus:.1f} {unit}', 'muted'))
        details = QWidget(); grid = QGridLayout(details); grid.setContentsMargins(0, 4, 0, 2)
        values = [('Overall baseline', f"{row['baseline_pct']:.2f}"),
                  ('Enemy adjustment', f"{row['matchup_points']:+.2f}"),
                  ('Ally adjustment', f"{row['synergy_points']:+.2f}"),
                  ('Total score', f"{row['score']:.2f}")]
        if 'opportunity_percentile' in row:
            values.extend([('Opportunity percentile', f"{row['opportunity_percentile']:.1f}"),
                           ('Above typical situation', f"{row['above_typical_points']:+.3f} points"),
                           ('Reference matches', f"{row['opportunity_reference_count']:,}")])
            from datetime import datetime, timezone
            downloaded = datetime.fromisoformat(row['opportunity_reference_downloaded_at'])
            age = max(0, (datetime.now(timezone.utc) - downloaded).total_seconds()/3600)
            values.append(('Reference age', f'{age:.1f} hours'))
        for i, (key, value) in enumerate(values):
            grid.addWidget(label(key, 'muted'), i, 0)
            v = label(value); v.setAlignment(Qt.AlignmentFlag.AlignRight); grid.addWidget(v, i, 1)
        warning = []
        if row.get('opportunity_reference_count', 500) < 500: warning.append('Limited reference sample; percentile is less stable.')
        if row.get('missing'): warning.append('Missing pair data: ' + ', '.join(row['missing']))
        if warning: grid.addWidget(label('\n'.join(warning), 'muted', True), len(values), 0, 1, 2)
        self.disclosure = Disclosure('Score breakdown', details, expanded)
        outer.addWidget(self.disclosure)


def build_interface(w, modes):
    w.setStyleSheet(STYLE); w.resize(690, 900); w.setMinimumSize(600, 620)
    outer = QVBoxLayout(w); outer.setContentsMargins(20, 12, 20, 12); outer.setSpacing(8)
    head = QHBoxLayout(); head.addWidget(Emblem())
    titles = QVBoxLayout(); titles.setSpacing(0)
    titles.addWidget(label('DEADLOCK', 'title')); titles.addWidget(label('C O M P A N I O N', 'eyebrow'))
    head.addLayout(titles); head.addStretch()
    head.addWidget(label('DESIGN PREVIEW' if w.preview else 'PREGAME ASSISTANT', 'eyebrow'))
    outer.addLayout(head)
    w.status = label('Starting detection and loading statistics…', 'status', True); outer.addWidget(w.status)
    controls = QHBoxLayout()
    w.mode = QComboBox(); w.mode.addItems(modes); w.mode.setCurrentText('Best Opportunity')
    w.mode.setAccessibleName('Recommendation mode')
    w.edit_roster_button = QPushButton('Edit roster'); w.edit_roster_button.clicked.connect(w.edit_roster)
    controls.addWidget(w.mode, 1); controls.addWidget(w.edit_roster_button); outer.addLayout(controls)
    controls = QHBoxLayout()
    w.balance = QCheckBox('Balance roster'); w.balance.setChecked(w.history.enabled())
    w.balance.setToolTip('Favour heroes with fewer previous #1 recommendations. Counts are recorded with this on or off.')
    w.balance.toggled.connect(w.balance_changed)
    w.reset_counts_button = QPushButton('Reset counts'); w.reset_counts_button.setObjectName('quiet')
    w.reset_counts_button.clicked.connect(w.reset_balance_counts)
    controls.addWidget(w.balance); controls.addStretch(); controls.addWidget(w.reset_counts_button); outer.addLayout(controls)
    w.history_label = label(f'{sum(w.history.counts().values())} counted pregame recommendations.', 'muted', True)
    outer.addWidget(w.history_label)
    w.scroll = QScrollArea(); w.scroll.setWidgetResizable(True)
    w.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    body = QWidget(); w.cards_layout = QVBoxLayout(body); w.cards_layout.setContentsMargins(0, 6, 6, 6)
    w.cards_layout.setSpacing(10); w.cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
    w.scroll.setWidget(body); outer.addWidget(w.scroll, 1)
    row = QHBoxLayout()
    w.reroll = QPushButton('Reroll'); w.reroll.setEnabled(False)
    row.addWidget(w.reroll); row.addWidget(label('Available in Random mode', 'muted')); row.addStretch()
    outer.addLayout(row)
    w.notice = label('', 'muted', True); outer.addWidget(w.notice)
    w.log = QPlainTextEdit(); w.log.setReadOnly(True); w.log.setMaximumBlockCount(150); w.log.setFixedHeight(100)
    w.activity = Disclosure('Activity log', w.log, False); outer.addWidget(w.activity)
    footer = 'Preview uses example data. Your saved roster and counts are untouched.' if w.preview else 'Hero artwork © Valve · Independent companion app'
    outer.addWidget(label(footer, 'muted', True))
    clear_cards(w, 'Waiting for a confirmed pregame lineup')


def clear_cards(w, message):
    while w.cards_layout.count():
        item = w.cards_layout.takeAt(0)
        if item.widget():
            item.widget().hide()
            item.widget().deleteLater()
    w.pick_cards = []
    empty = label(message, 'heading', True); w.cards_layout.addWidget(empty)
    w.cards_layout.addWidget(label('Open a competitive pregame to see your picks.', 'muted', True))
    w.notice.setText('Scores are estimates, not win probabilities.\nEnemy picks can change. Confirm availability in game.')


def show_cards(w, data, selected, bonuses):
    expanded = {c.hero: c.disclosure.button.isChecked() for c in getattr(w, 'pick_cards', [])}
    scroll_value = w.scroll.verticalScrollBar().value()
    clear_cards(w, '')
    while w.cards_layout.count():
        item = w.cards_layout.takeAt(0)
        if item.widget():
            item.widget().hide()
            item.widget().deleteLater()
    rows = {r['hero']: r for r in data['ranked']}; current = rows[data['current_hero']]
    frame = QFrame(); frame.setObjectName('current'); box = QHBoxLayout(frame)
    box.addWidget(Portrait(data['current_hero'], 34, 46)); names = QVBoxLayout()
    names.addWidget(label('YOU ARE PLAYING', 'eyebrow')); names.addWidget(label(display_name(data['current_hero'])))
    box.addLayout(names, 1); box.addWidget(label(f"{current['score']:.2f} score", 'muted')); w.cards_layout.addWidget(frame)
    w.cards_layout.addWidget(label('Your picks', 'heading'))
    mode = w.mode.currentText()
    for position, hero in enumerate(selected, 1):
        row = dict(rows[hero]); row['difference'] = row['score'] - current['score']
        card = PickCard(row, position, mode, w.prior_counts.get(hero, 0), bonuses.get(hero), data['current_hero'], expanded.get(hero, False))
        w.pick_cards.append(card); w.cards_layout.addWidget(card)
    if not selected:
        w.cards_layout.addWidget(label('Opportunity reference data is unavailable for these candidates.', 'muted', True))
    if mode == 'Best Opportunity':
        text = 'Ranked by opportunity percentile' + (' plus balance preference.' if w.balance.isChecked() else '.')
        text += '\nPercentiles compare each hero’s usual situations, not win chance.'
    elif mode == 'Competitive':
        text = 'Ranked by score' + (' plus balance preference.' if w.balance.isChecked() else '.')
        text += '\nScore differences are not changes in win probability.'
    else:
        text = 'Random options weighted towards less recommended heroes.' if w.balance.isChecked() else 'Random options, not ranked by score.'
    w.notice.setText(text + '\nEnemy picks can change. Confirm availability in game.')
    w.scroll.verticalScrollBar().setValue(scroll_value)
