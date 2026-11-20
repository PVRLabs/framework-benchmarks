package pvrlabs.marketreplay;

import io.micronaut.core.annotation.Nullable;
import io.micronaut.http.HttpResponse;
import io.micronaut.http.HttpStatus;
import io.micronaut.http.MediaType;
import io.micronaut.http.annotation.Body;
import io.micronaut.http.annotation.Controller;
import io.micronaut.http.annotation.Error;
import io.micronaut.http.annotation.Get;
import io.micronaut.http.annotation.Put;
import io.micronaut.scheduling.TaskExecutors;
import io.micronaut.scheduling.annotation.ExecuteOn;

import java.math.BigDecimal;
import java.util.List;
import java.util.Map;

@Controller
@ExecuteOn(TaskExecutors.BLOCKING)
class PortfolioController {
    private final PortfolioService portfolios;
    private final PortfolioRepository repository;
    private final QuoteRepository quotes;

    PortfolioController(PortfolioService portfolios, PortfolioRepository repository, QuoteRepository quotes) {
        this.portfolios = portfolios;
        this.repository = repository;
        this.quotes = quotes;
    }

    record QuantityRequest(BigDecimal quantity) {}

    @Get("/users/{id}/portfolio")
    Portfolio portfolio(long id) {
        return portfolios.portfolio(id);
    }

    @Get("/users/{id}/valuation")
    Valuation valuation(long id) {
        return new Valuation(id, portfolios.portfolio(id).totalValue());
    }

    @Put("/users/{id}/holdings/{symbol}")
    HttpResponse<Void> set(long id, String symbol, @Body @Nullable QuantityRequest body) {
        portfolios.setQuantity(id, symbol, body == null ? null : body.quantity());
        return HttpResponse.noContent();
    }

    @Get("/api/quotes/latest")
    List<QuoteObservation> latest() {
        return quotes.latest();
    }

    @Get("/api/quotes/history")
    List<QuoteObservation> history() {
        return quotes.history();
    }

    @Get("/readyz")
    HttpResponse<Map<String, String>> ready() {
        try {
            return status(repository.findSeedUserCount().isPresent() && quotes.hasMarketPrices());
        } catch (RuntimeException e) {
            return status(false);
        }
    }

    @Get("/actuator/health")
    HttpResponse<Map<String, String>> health() {
        try {
            return status(repository.databasePing() == 1);
        } catch (RuntimeException e) {
            return status(false);
        }
    }

    @Error
    HttpResponse<Map<String, Object>> invalidHolding(InvalidHoldingException e) {
        return problem(HttpStatus.BAD_REQUEST, e);
    }

    @Error
    HttpResponse<Map<String, Object>> missingUser(UserNotFoundException e) {
        return problem(HttpStatus.NOT_FOUND, e);
    }

    @Error
    HttpResponse<Map<String, Object>> missingPrices(MarketPricesUnavailableException e) {
        return problem(HttpStatus.SERVICE_UNAVAILABLE, e);
    }

    private HttpResponse<Map<String, Object>> problem(HttpStatus status, RuntimeException error) {
        return HttpResponse.<Map<String, Object>>status(status)
                .contentType(MediaType.of("application/problem+json"))
                .body(Map.of("status", status.getCode(), "detail", error.getMessage()));
    }

    private HttpResponse<Map<String, String>> status(boolean up) {
        return HttpResponse.<Map<String, String>>status(up ? HttpStatus.OK : HttpStatus.SERVICE_UNAVAILABLE)
                .body(Map.of("status", up ? "UP" : "DOWN"));
    }
}
