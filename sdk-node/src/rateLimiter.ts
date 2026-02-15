export class RateLimiter {
  public allow(_key: string): boolean {
    // TODO: Implement local sliding-window rate limiting.
    return true;
  }
}
