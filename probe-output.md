
## Auth

- **no key** → 401 `application/json` 6064ms
  ```
  {"error":"Invalid or missing API key"}
  ```
- **wrong key** → 401 `application/json` 358ms
  ```
  {"error":"Invalid or missing API key"}
  ```
- **lowercase header** → 200 `application/json` 711ms
  ```
  {"location":"London","conditions":[{"temperature_c":10.4,"condition":"Moderate rain","humidity":66},{"temperature_c":9.4,"condition":"light rain","humidity":79}],"note":"Multiple conditions reported"}
  ```

## Weather params

- **happy** → 200 `application/json` 435ms
  ```
  {"location":"London","conditions":[{"temperature_c":10.4,"condition":"Moderate rain","humidity":66},{"temperature_c":9.4,"condition":"light rain","humidity":79}],"note":"Multiple conditions reported"}
  ```
- **missing** → 422 `application/json` 363ms
  ```
  {"detail":[{"type":"missing","loc":["query","location"],"msg":"Field required","input":null}]}
  ```
- **empty** → 404 `application/json` 445ms
  ```
  {"error":"Location \"\" not found"}
  ```
- **unicode** → 200 `application/json` 452ms
  ```
  {"location":"Sao Paulo","temperature_c":12.1,"condition":"Mist","humidity":94}
  ```
- **very long** → 404 `application/json` 447ms
  ```
  {"error":"Location \"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
  ```
- **whitespace** → 200 `application/json` 352ms
  ```
  {"status":"throttled","message":"Rate limit exceeded. Please wait.","retry_after_seconds":27,"data":null}
  ```
- **unknown extra** → 200 `application/json` 344ms
  ```
  {"status":"throttled","message":"Rate limit exceeded. Please wait.","retry_after_seconds":26,"data":null}
  ```

## Research params

- **happy** → 200 `application/json` 352ms
  ```
  {"status":"throttled","message":"Rate limit exceeded. Please wait.","retry_after_seconds":26,"data":null}
  ```
- **missing** → 422 `application/json` 347ms
  ```
  {"detail":[{"type":"missing","loc":["query","topic"],"msg":"Field required","input":null}]}
  ```
- **empty** → 200 `application/json` 351ms
  ```
  {"status":"throttled","message":"Rate limit exceeded. Please wait.","retry_after_seconds":25,"data":null}
  ```
- **encoded space** → 200 `application/json` 404ms
  ```
  {"status":"throttled","message":"Rate limit exceeded. Please wait.","retry_after_seconds":25,"data":null}
  ```
- **unicode** → 200 `application/json` 356ms
  ```
  {"status":"throttled","message":"Rate limit exceeded. Please wait.","retry_after_seconds":24,"data":null}
  ```

## Determinism — weather

- **London #1** → 200 `application/json` 345ms
  ```
  {"status":"throttled","message":"Rate limit exceeded. Please wait.","retry_after_seconds":24,"data":null}
  ```
- **London #2** → 200 `application/json` 422ms
  ```
  {"status":"throttled","message":"Rate limit exceeded. Please wait.","retry_after_seconds":24,"data":null}
  ```
- **London #3** → 200 `application/json` 412ms
  ```
  {"status":"throttled","message":"Rate limit exceeded. Please wait.","retry_after_seconds":23,"data":null}
  ```

## Determinism — research

- **solar #1** → 200 `application/json` 353ms
  ```
  {"status":"throttled","message":"Rate limit exceeded. Please wait.","retry_after_seconds":23,"data":null}
  ```
- **solar #2** → 200 `application/json` 347ms
  ```
  {"status":"throttled","message":"Rate limit exceeded. Please wait.","retry_after_seconds":23,"data":null}
  ```
- **solar #3** → 200 `application/json` 355ms
  ```
  {"status":"throttled","message":"Rate limit exceeded. Please wait.","retry_after_seconds":22,"data":null}
  ```

## Timing — /weather (5 calls)

- n=5, p50=347ms, min=344ms, max=356ms

## Timing — /research (3 calls)

- n=3, p50=349ms, min=347ms, max=357ms

## Concurrency — 5 parallel /research

- total wall: 781ms
  - task 0: 200 105 bytes
  - task 1: 200 105 bytes
  - task 2: 200 105 bytes
  - task 3: 200 105 bytes
  - task 4: 200 105 bytes
