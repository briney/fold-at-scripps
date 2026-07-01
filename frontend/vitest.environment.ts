import { builtinEnvironments, type Environment } from "vitest/runtime";

/**
 * jsdom's File/Blob/FormData/Request are separate classes from the ones
 * Node's native fetch() uses internally (undici). MSW's Node interceptors
 * and undici's own body serializer rely on `instanceof` checks against the
 * *native* classes, so a FormData/File built from jsdom's globals silently
 * fails to encode as multipart bytes (it gets stringified instead).
 *
 * This wraps the built-in "jsdom" environment and restores Node's native
 * fetch/File/Blob/FormData/Request/Response/Headers globals after jsdom
 * installs its own, so tests that upload files via fetch() work the same
 * way they would in a browser talking to a real server, while everything
 * else (DOM, window, etc.) still comes from jsdom.
 */
const jsdomEnvironment = builtinEnvironments.jsdom;

const nativeFetch = globalThis.fetch;
const nativeFile = globalThis.File;
const nativeBlob = globalThis.Blob;
const nativeFormData = globalThis.FormData;
const nativeRequest = globalThis.Request;
const nativeResponse = globalThis.Response;
const nativeHeaders = globalThis.Headers;

const environment: Environment = {
  ...jsdomEnvironment,
  name: "jsdom-native-fetch",
  async setup(global, options) {
    const result = await jsdomEnvironment.setup(global, options);
    Object.assign(global, {
      fetch: nativeFetch,
      File: nativeFile,
      Blob: nativeBlob,
      FormData: nativeFormData,
      Request: nativeRequest,
      Response: nativeResponse,
      Headers: nativeHeaders,
    });
    return result;
  },
};

export default environment;
