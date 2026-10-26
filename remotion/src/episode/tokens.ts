// Geometry and motion — the same for every theme (colours/fonts live in theme.ts).
export const FPS = 30;
export const W = 1920;
export const H = 1080;

// Motion: no bounce, short entrances, shorter exits.
export const SPRING = {damping: 200, mass: 0.6};
export const ENTER = 12;
export const EXIT = 8;
export const LAYOUT_MOVE = 20; // frames for a layout change
export const ZOOM_MOVE = 24;
export const CHROME = 44; // window title bar height

export type Rect = {x: number; y: number; w: number; h: number; r: number};

// "talk" = speaker window, "screen" = screen window + camera bubble.
export const LAYOUT: Record<'talk' | 'screen', {cam: Rect; screen: Rect; screenOpacity: number}> = {
  talk: {
    cam: {x: W - 110 - 500, y: 110, w: 500, h: 830, r: 18},
    screen: {x: 90, y: 150, w: 1400, h: 788, r: 18},
    screenOpacity: 0,
  },
  screen: {
    cam: {x: W - 60 - 290, y: 640, w: 290, h: 290, r: 145},
    screen: {x: 60, y: 110, w: 1480, h: 832, r: 18},
    screenOpacity: 1,
  },
};
