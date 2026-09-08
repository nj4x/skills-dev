# Colorblind-safe palette

Default colorblind-safe palette (Okabe-Ito, safe for deuteranopia/protanopia/tritanopia):

```css
:root {
  --bg:           #ffffff;
  --bg-alt:       #f5f5f5;
  --text:         #1a1a1a;
  --text-muted:   #6b6b6b;
  --primary:      #0072b2;   /* blue — universally safe */
  --secondary:    #e69f00;   /* orange */
  --accent-green: #009e73;   /* bluish-green */
  --accent-red:   #d55e00;   /* vermillion — distinguishable from green */
  --border:       #d0d0d0;
  --radius:       6px;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg:           #1a1a1a;
    --bg-alt:       #252525;
    --text:         #f0f0f0;
    --text-muted:   #9a9a9a;
    --primary:      #56b4e9;   /* sky blue */
    --secondary:    #f0e442;   /* yellow */
    --accent-green: #009e73;
    --accent-red:   #e06c3a;
    --border:       #3a3a3a;
  }
}
```

Rules: (1) never use red/green as the **only** differentiator in tables, status badges, or charts; pair color with a shape/icon/label; (2) use `--primary` (blue) for the main interactive accent; (3) if you need a third categorical color beyond primary+secondary, use `--accent-green`; (4) error states use `--accent-red` with an icon (`⚠`) or text label ("Error"), not color alone.
