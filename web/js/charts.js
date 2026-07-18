// charts.js — Custom canvas charts for Rask (no external chart library).
//   ProgressRing.draw(ctx, x, y, size, progress, color, trackColor, label)
//   BarChart.draw(ctx, x, y, w, h, data, opts)
//   DonutChart.draw(ctx, cx, cy, r, data, lineWidth)
//   Heatmap.draw(ctx, x, y, w, h, year, data, cellSize)
window.RaskCharts = (function () {
  function hexToRgba(hex, alpha) {
    hex = (hex || "#D4AF37").replace("#", "");
    if (hex.length === 3) hex = hex.split("").map((c) => c + c).join("");
    const r = parseInt(hex.slice(0, 2), 16);
    const g = parseInt(hex.slice(2, 4), 16);
    const b = parseInt(hex.slice(4, 6), 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha == null ? 1 : alpha})`;
  }

  const ProgressRing = {
    draw(ctx, cx, cy, size, progress, color, trackColor, label, labelColor) {
      progress = Math.max(0, Math.min(1, progress));
      const r = size / 2 - 8;
      const lw = 8;
      ctx.clearRect(cx - size/2 - 2, cy - size/2 - 2, size + 4, size + 4);
      // Track
      ctx.beginPath();
      ctx.strokeStyle = trackColor || "#2C2C30";
      ctx.lineWidth = lw;
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.stroke();
      // Progress (start at top, go clockwise)
      if (progress > 0) {
        ctx.beginPath();
        ctx.strokeStyle = color || "#D4AF37";
        ctx.lineWidth = lw;
        ctx.lineCap = "round";
        ctx.arc(cx, cy, r, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * progress);
        ctx.stroke();
      }
      // Label
      if (label) {
        ctx.fillStyle = labelColor || "#E8E8E8";
        ctx.font = `bold ${Math.floor(size * 0.16)}px Vazirmatn, sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(label, cx, cy);
      }
    }
  };

  const BarChart = {
    // data: [{label, value, color}]
    draw(ctx, x, y, w, h, data, opts) {
      opts = opts || {};
      ctx.clearRect(x, y, w, h);
      if (!data || !data.length) return;
      const maxVal = opts.maxValue || Math.max.apply(null, data.map((d) => d.value).concat([1]));
      const gap = 6;
      const barW = Math.max(2, (w - gap * (data.length + 1)) / data.length);
      // Baseline
      ctx.strokeStyle = "#2C2C30";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x, y + h - 18);
      ctx.lineTo(x + w, y + h - 18);
      ctx.stroke();
      // Bars
      data.forEach((d, i) => {
        const bh = maxVal > 0 ? (d.value / maxVal) * (h - 30) : 0;
        const bx = x + gap + i * (barW + gap);
        const by = y + h - 18 - bh;
        ctx.fillStyle = d.color || "#D4AF37";
        // Rounded top
        const radius = Math.min(3, barW / 2);
        ctx.beginPath();
        ctx.moveTo(bx, by + radius);
        ctx.arcTo(bx, by, bx + radius, by, radius);
        ctx.lineTo(bx + barW - radius, by);
        ctx.arcTo(bx + barW, by, bx + barW, by + radius, radius);
        ctx.lineTo(bx + barW, by + bh);
        ctx.lineTo(bx, by + bh);
        ctx.closePath();
        ctx.fill();
        // Label
        if (d.label) {
          ctx.fillStyle = "#9A9A9F";
          ctx.font = "10px Vazirmatn, sans-serif";
          ctx.textAlign = "center";
          ctx.textBaseline = "top";
          ctx.fillText(d.label, bx + barW / 2, y + h - 14);
        }
      });
    }
  };

  const DonutChart = {
    // data: [{label, value, color}]
    draw(ctx, cx, cy, r, data, lineWidth) {
      lineWidth = lineWidth || 18;
      ctx.save();
      // Clear area
      ctx.clearRect(cx - r - lineWidth, cy - r - lineWidth,
                    (r + lineWidth) * 2, (r + lineWidth) * 2);
      const total = data.reduce((s, d) => s + d.value, 0) || 1;
      // Track
      ctx.beginPath();
      ctx.strokeStyle = "#2C2C30";
      ctx.lineWidth = lineWidth;
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.stroke();
      // Segments
      let angle = -Math.PI / 2;
      data.forEach((d) => {
        if (!d.value) return;
        const seg = (d.value / total) * Math.PI * 2;
        ctx.beginPath();
        ctx.strokeStyle = d.color || "#D4AF37";
        ctx.lineWidth = lineWidth;
        ctx.lineCap = "butt";
        ctx.arc(cx, cy, r, angle, angle + seg);
        ctx.stroke();
        angle += seg;
      });
      ctx.restore();
    }
  };

  const Heatmap = {
    // data: { "YYYY-MM-DD": seconds }
    draw(ctx, x, y, w, h, year, data, cellSize) {
      cellSize = cellSize || 12;
      const gap = 3;
      ctx.clearRect(x, y, w, h);
      const max = Math.max.apply(null, Object.values(data).concat([1]));
      const start = new Date(year, 0, 1);
      // Find Sunday of first week
      const offset = (start.getDay() + 1) % 7;
      const cursor = new Date(start);
      cursor.setDate(cursor.getDate() - offset);
      const end = new Date(year, 11, 31);
      let col = 0;
      while (cursor <= end) {
        for (let row = 0; row < 7; row++) {
          if (cursor.getFullYear() === year) {
            const iso = cursor.toISOString().slice(0, 10);
            const sec = data[iso] || 0;
            const t = max > 0 ? sec / max : 0;
            const color = Heatmap.intensityColor(t);
            ctx.fillStyle = color;
            ctx.fillRect(
              x + col * (cellSize + gap),
              y + row * (cellSize + gap),
              cellSize, cellSize
            );
          }
          cursor.setDate(cursor.getDate() + 1);
        }
        col++;
      }
    },
    intensityColor(t) {
      const steps = [
        "rgba(14,14,16,1)",
        "rgba(48,40,16,1)",
        "rgba(80,64,20,1)",
        "rgba(120,96,28,1)",
        "rgba(212,175,55,1)",
      ];
      const idx = Math.min(steps.length - 1, Math.floor(t * steps.length));
      return steps[idx];
    }
  };

  return { hexToRgba, ProgressRing, BarChart, DonutChart, Heatmap };
})();
