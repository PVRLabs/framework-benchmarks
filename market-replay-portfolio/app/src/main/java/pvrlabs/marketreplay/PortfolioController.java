package pvrlabs.marketreplay;

import org.springframework.http.HttpStatus;
import java.math.BigDecimal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
class PortfolioController {
    record QuantityRequest(BigDecimal quantity) {}

    private final PortfolioService service;
    PortfolioController(PortfolioService service) { this.service = service; }

    @GetMapping("/users/{id}/portfolio")
    Portfolio portfolio(@PathVariable long id) { return service.portfolio(id); }

    @GetMapping("/users/{id}/valuation")
    Valuation valuation(@PathVariable long id) {
        Portfolio portfolio = service.portfolio(id);
        return new Valuation(id, portfolio.totalValue());
    }

    @PutMapping("/users/{id}/holdings/{symbol}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    void set(@PathVariable long id, @PathVariable String symbol, @RequestBody QuantityRequest request) {
        service.setQuantity(id, symbol, request == null ? null : request.quantity());
    }
}
