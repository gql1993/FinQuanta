import os, sys, sqlite3
os.environ['QT_OPENGL'] = 'software'
sys.path.insert(0, '.')
import numpy as np
from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtCore import QTimer, Qt
import pyqtgraph as pg
pg.setConfigOptions(antialias=True)

app = QApplication(sys.argv)
w = QMainWindow()
chart = pg.PlotWidget()
chart.setBackground('#1a1a2e')
w.setCentralWidget(chart)
w.resize(800, 500)

conn = sqlite3.connect('data_cache/quant.db')
cur = conn.execute("SELECT open,high,low,close FROM daily_kline WHERE code='002975' ORDER BY date")
rows = cur.fetchall()
conn.close()
print(f'{len(rows)} rows')

n = min(len(rows), 250)
o = np.array([float(r[0]) for r in rows[-n:]])
h = np.array([float(r[1]) for r in rows[-n:]])
l = np.array([float(r[2]) for r in rows[-n:]])
c = np.array([float(r[3]) for r in rows[-n:]])

up = c >= o
dn = ~up
for mask, color in [(up, '#ef5350'), (dn, '#26a69a')]:
    xs = np.where(mask)[0]
    if len(xs) == 0:
        continue
    bb = np.minimum(o[mask], c[mask])
    bt = np.maximum(o[mask], c[mask])
    bh = np.maximum(bt - bb, 0.01)
    chart.addItem(pg.BarGraphItem(x=xs, height=bh, width=0.6, y0=bb,
                                   brush=QColor(color), pen=pg.mkPen(color, width=0.5)))
    wx, wy = [], []
    for i in range(len(xs)):
        wx.extend([xs[i], xs[i], np.nan])
        wy.extend([l[mask][i], h[mask][i], np.nan])
    chart.plot(wx, wy, pen=pg.mkPen(color, width=0.8), connect='finite')

print('K-line drawn')

# prediction lines
for i in range(8):
    rng = np.random.RandomState(42 + i)
    path = [float(c[-1])]
    for d in range(20):
        path.append(path[-1] + rng.normal(0, 1))
    chart.plot(np.arange(n - 1, n - 1 + 21), path, pen=pg.mkPen(width=2))

print('predictions drawn')
chart.autoRange()
print('all done, showing window')
w.show()
QTimer.singleShot(5000, app.quit)
sys.exit(app.exec())
