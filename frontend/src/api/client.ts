export interface ApiClient {
  get<T>(path: string): Promise<T>;
  post<TRequest, TResponse>(path: string, payload: TRequest): Promise<TResponse>;
}

export class HttpApiClient implements ApiClient {
  public async get<T>(_path: string): Promise<T> {
    // TODO: Implement typed GET request handling.
    throw new Error("Not implemented");
  }

  public async post<TRequest, TResponse>(
    _path: string,
    _payload: TRequest,
  ): Promise<TResponse> {
    // TODO: Implement typed POST request handling.
    throw new Error("Not implemented");
  }
}
