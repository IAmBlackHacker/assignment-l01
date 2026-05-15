# Targeted re-probe — 2026-05-14 15:56:48
# Delay between requests: 12s

### research/solar #1
Status: 200  Content-Type: application/json  Time: 6653ms
Body: {"topic":"solar energy","summary":"Research summary for 'solar energy'. This analysis covers key aspects and recent developments in the field.","sources":["nature.com","sciencedirect.com","arxiv.org"],"generated_at":"2026-05-14T10:26:54.821307+00:00"}

### research/solar #2
Status: 200  Content-Type: application/json  Time: 4090ms
Body: {"topic":"solar energy","summary":"Research summary for 'solar energy'. This analysis covers key aspects and recent developments in the field.","sources":["nature.com","sciencedirect.com","arxiv.org"],"generated_at":"2026-05-14T10:27:10.924514+00:00"}

### research/solar #3
Status: 200  Content-Type: application/json  Time: 8201ms
Body: {"topic":"solar energy","summary":"Research summary for 'solar energy'. This analysis covers key aspects and recent developments in the field.","sources":["nature.com","sciencedirect.com","arxiv.org"],"generated_at":"2026-05-14T10:27:31.122728+00:00"}

### research/empty
Status: 200  Content-Type: application/json  Time: 4412ms
Body: {"topic":"","summary":"Research on '' from early 2024. This cached summary may not reflect recent developments.","sources":["nature.com","sciencedirect.com","arxiv.org"],"generated_at":"2024-03-15T09:00:00Z","cached":true,"cache_age_seconds":26784000}

### research/unicode café
Status: 200  Content-Type: application/json  Time: 5000ms
Body: {"topic":"café science","summary":"Research on 'café science' from early 2024. This cached summary may not reflect recent developments.","sources":["nature.com","sciencedirect.com","arxiv.org"],"generated_at":"2024-03-15T09:00:00Z","cached":true,"cache_age_seconds":26784000}

### weather/London
Status: 200  Content-Type: application/json  Time: 852ms
Body: {"location":"London","temperature_c":10.4,"condition":"Moderate rain","humidity":66}

### weather/Tokyo
Status: 200  Content-Type: application/json  Time: 577ms
Body: {"location":"Tokyo","conditions":[{"temperature_c":18.3,"condition":"Partly cloudy","humidity":77},{"temperature_c":17.3,"condition":"light rain","humidity":90}],"note":"Multiple conditions reported"}

### weather/whitespace-location
Status: 200  Content-Type: application/json  Time: 856ms
Body: {"location":"London","conditions":[{"temperature_c":10.4,"condition":"Moderate rain","humidity":66},{"temperature_c":9.4,"condition":"light rain","humidity":79}],"note":"Multiple conditions reported"}

### research/missing-param
Status: 422  Content-Type: application/json  Time: 473ms
Body: {"detail":[{"type":"missing","loc":["query","topic"],"msg":"Field required","input":null}]}

### research/extra-param
Status: 200  Content-Type: application/json  Time: 4430ms
Body: {"topic":"solar energy","summary":"Research summary for 'solar energy'. This analysis covers key aspects and recent developments in the field.","sources":["nature.com","sciencedirect.com","arxiv.org"],"generated_at":"2026-05-14T10:29:11.746270+00:00"}

# Done
