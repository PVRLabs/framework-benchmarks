package pvrlabs.marketreplay;

import io.avaje.http.api.*;

import java.math.BigDecimal;

@Controller
public final class PortfolioController {
    private final PortfolioService portfolios;
    private final QuoteRepository quotes;

    public PortfolioController(PortfolioService portfolios, QuoteRepository quotes) {
        this.portfolios = portfolios;
        this.quotes = quotes;
    }

    public record QuantityRequest(BigDecimal quantity) {}

    @Get("/users/{id}/portfolio")
    public Portfolio portfolio(long id) {
        return portfolios.portfolio(id);
    }

    @Get("/users/{id}/valuation")
    public Valuation valuation(long id) {
        return new Valuation(id, portfolios.portfolio(id).totalValue());
    }

    @Put("/users/{id}/holdings/{symbol}")
    @Produces(statusCode = 204)
    public void set(long id, String symbol, QuantityRequest input) {
        portfolios.setQuantity(id, symbol, input == null ? null : input.quantity());
    }

    @Get("/api/quotes/latest")
    public java.util.List<QuoteObservation> latest() {
        return quotes.latest();
    }

    @Get("/api/quotes/history")
    public java.util.List<QuoteObservation> history() {
        return quotes.history();
    }
}
