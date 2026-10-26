import React from 'react';
import {Composition} from 'remotion';
import {Episode, calculateEpisodeMetadata, EPISODE_FPS} from './episode/Episode';

export const RemotionRoot: React.FC = () => (
  <Composition
    id="EpisodeYouTube"
    component={Episode}
    calculateMetadata={calculateEpisodeMetadata}
    defaultProps={{episode: 'example'}}
    durationInFrames={300}
    fps={EPISODE_FPS}
    width={1920}
    height={1080}
  />
);
