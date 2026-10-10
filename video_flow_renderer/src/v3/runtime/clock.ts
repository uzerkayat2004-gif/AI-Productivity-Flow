/**
 * Absolute-Time Master Clock for Video Flow V3.
 * Guarantees state = Scene(t) determinism without frame drift across 30fps/60fps playback & export.
 */

export class AbsoluteTimeClock {
  private _timeSec: number = 0;
  private _durationSec: number = 0;
  private _isPlaying: boolean = false;
  private _lastRealTime: number = 0;

  constructor(durationSec: number = 0) {
    this._durationSec = durationSec;
  }

  public setDuration(durationSec: number): void {
    this._durationSec = Math.max(0, durationSec);
  }

  public getTime(): number {
    return this._timeSec;
  }

  public getDuration(): number {
    return this._durationSec;
  }

  public isPlaying(): boolean {
    return this._isPlaying;
  }

  public play(): void {
    this._isPlaying = true;
    this._lastRealTime = performance.now();
  }

  public pause(): void {
    this._isPlaying = false;
  }

  public seek(timeSec: number): void {
    this._timeSec = Math.max(0, Math.min(this._durationSec, timeSec));
  }

  public tick(): number {
    if (!this._isPlaying) {
      return this._timeSec;
    }
    const now = performance.now();
    const dt = (now - this._lastRealTime) / 1000.0;
    this._lastRealTime = now;

    this._timeSec += dt;
    if (this._timeSec >= this._durationSec) {
      this._timeSec = this._durationSec;
      this._isPlaying = false;
    }
    return this._timeSec;
  }
}
