package pvrlabs.marketreplay;

import io.micronaut.json.JsonMapper;

import jakarta.inject.Singleton;

import io.micronaut.context.annotation.Value;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

@Singleton
class QuoteClient {
    private final URI quotesUri;
    private final HttpClient httpClient;
    private final JsonMapper jsonMapper;

    QuoteClient(
            @Value("${market.fixture-url:http://127.0.0.1:8090/quotes}")
                    URI quotesUri,
            JsonMapper jsonMapper) {
        this.quotesUri = quotesUri;
        this.jsonMapper = jsonMapper;
        this.httpClient = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(3)).build();
    }

    QuoteBatch fetch() throws IOException, InterruptedException {
        HttpRequest request =
                HttpRequest.newBuilder(quotesUri).timeout(Duration.ofSeconds(5)).GET().build();
        HttpResponse<byte[]> response =
                httpClient.send(request, HttpResponse.BodyHandlers.ofByteArray());
        if (response.statusCode() != 200) {
            throw new IOException("fixture returned HTTP " + response.statusCode());
        }
        return jsonMapper.readValue(response.body(), QuoteBatch.class);
    }
}
