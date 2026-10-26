// Theme = the identity of a channel (colours, fonts, name, sounds). Lives in
// public/themes/<name>.json so the dashboard can edit it; components read it via useTheme().
import {createContext, useContext} from 'react';
import {staticFile} from 'remotion';
import {loadFont as cairo} from '@remotion/google-fonts/Cairo';
import {loadFont as fira} from '@remotion/google-fonts/FiraCode';
import {loadFont as inter} from '@remotion/google-fonts/Inter';
import {loadFont as plexAr} from '@remotion/google-fonts/IBMPlexSansArabic';
import {loadFont as jetbrains} from '@remotion/google-fonts/JetBrainsMono';
import {loadFont as readex} from '@remotion/google-fonts/ReadexPro';
import {loadFont as tajawal} from '@remotion/google-fonts/Tajawal';

const W3 = {weights: ['400', '500', '700'] as string[]};
// Every font a theme may pick. Loaded once; the theme only chooses by name.
export const FONTS: Record<string, string> = {
  'IBM Plex Sans Arabic': plexAr('normal', {...W3, subsets: ['arabic', 'latin']} as any).fontFamily,
  Tajawal: tajawal('normal', {weights: ['500', '700', '800'], subsets: ['arabic', 'latin']} as any).fontFamily,
  Cairo: cairo('normal', {weights: ['500', '700', '800'], subsets: ['arabic', 'latin']} as any).fontFamily,
  'Readex Pro': readex('normal', {...W3, subsets: ['arabic', 'latin']} as any).fontFamily,
  'JetBrains Mono': jetbrains('normal', {weights: ['500', '700', '800'], subsets: ['latin']} as any).fontFamily,
  'Fira Code': fira('normal', {weights: ['500', '700'], subsets: ['latin']} as any).fontFamily,
  Inter: inter('normal', {weights: ['500', '700', '800'], subsets: ['latin']} as any).fontFamily,
};

export type Theme = {
  name: string;
  label?: string;
  colors: {bg: string; glow: string; primary: string; accent: string; text: string; muted: string; card: string; line: string; paper: string; ink: string};
  fonts: {ar: string; mono: string};
  radius: number;
  grid: boolean;
  identity: {name: string; handle: string; role: string; path: string; logo: string; series: string};
  captions: {show: boolean; size: number; maxWords: number};
  keywords: {icons: boolean; size: number};
  music: {on: boolean; file: string; volume: number};
  sfx: {on: boolean; volume: number};
};

export const ThemeCtx = createContext<Theme | null>(null);
export const useTheme = () => {
  const t = useContext(ThemeCtx);
  if (!t) throw new Error('ThemeCtx missing');
  return t;
};
export const font = (t: Theme, k: 'ar' | 'mono') => FONTS[t.fonts[k]] ?? t.fonts[k];

/** Media URLs: staticFile() inside Remotion; the dashboard Player passes its own resolver. */
export type AssetResolver = (path: string) => string;
export const AssetCtx = createContext<AssetResolver | null>(null);
export const useAsset = (): AssetResolver => useContext(AssetCtx) ?? staticFile;

/** 8-digit hex with alpha. */
export const alpha = (hex: string, a: number) => hex + Math.round(Math.max(0, Math.min(1, a)) * 255).toString(16).padStart(2, '0');
