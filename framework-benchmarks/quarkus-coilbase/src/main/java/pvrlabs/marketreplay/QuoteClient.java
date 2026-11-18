package pvrlabs.marketreplay;

import com.fasterxml.jackson.databind.ObjectMapper;

import jakarta.enterprise.context.ApplicationScoped;

import org.eclipse.microprofile.config.inject.ConfigProperty;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

@ApplicationScoped
class QuoteClient {
    private final URI quotesUri;
    private final HttpClient httpClient;
    private final ObjectMapper objectMapper;

    QuoteClient(
            @ConfigProperty(
                            name = "market.fixture-url",
                            defaultValue = "http://127.0.0.1:8090/quotes")
                    URI quotesUri,
            ObjectMapper objectMapper) {
        this.quotesUri = quotesUri;
        this.objectMapper = objectMapper;
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
        return objectMapper.readValue(response.body(), QuoteBatch.class);
    }
}
