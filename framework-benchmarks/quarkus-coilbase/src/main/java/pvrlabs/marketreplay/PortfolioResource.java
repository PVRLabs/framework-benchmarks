package pvrlabs.marketreplay;

import io.smallrye.common.annotation.Blocking;

import jakarta.inject.Inject;
import jakarta.ws.rs.Consumes;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.PUT;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.PathParam;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;

import pvrlabs.coilbase.RepositoryContext;

import java.math.BigDecimal;
import java.util.Map;

@Path("/")
@Produces(MediaType.APPLICATION_JSON)
@Blocking
public class PortfolioResource {
    @Inject PortfolioService portfolios;
    @Inject QuoteRepository quotes;
    @Inject RepositoryContext db;

    public record QuantityRequest(BigDecimal quantity) {}

    @GET
    @Path("users/{id}/portfolio")
    public Portfolio portfolio(@PathParam("id") long id) {
        return portfolios.portfolio(id);
    }

    @GET
    @Path("users/{id}/valuation")
    public Valuation valuation(@PathParam("id") long id) {
        return new Valuation(id, portfolios.portfolio(id).totalValue());
    }

    @PUT
    @Path("users/{id}/holdings/{symbol}")
    @Consumes(MediaType.APPLICATION_JSON)
    public void set(
            @PathParam("id") long id, @PathParam("symbol") String symbol, QuantityRequest body) {
        portfolios.setQuantity(id, symbol, body == null ? null : body.quantity());
    }

    @GET
    @Path("api/quotes/latest")
    public java.util.List<QuoteObservation> latest() {
        return quotes.latest();
    }

    @GET
    @Path("api/quotes/history")
    public java.util.List<QuoteObservation> history() {
        return quotes.history();
    }

    @GET
    @Path("readyz")
    public Response ready() {
        boolean up;
        try {
            up =
                    db.query(
                                            "SELECT count(*) FROM portfolio_seed WHERE id=1",
                                            q -> q.mapTo(Integer.class).one())
                                    == 1
                            && quotes.hasMarketPrices();
        } catch (Exception e) {
            up = false;
        }
        return status(up);
    }

    @GET
    @Path("actuator/health")
    public Response health() {
        try {
            db.query("SELECT 1", q -> q.mapTo(Integer.class).one());
            return status(true);
        } catch (Exception e) {
            return status(false);
        }
    }

    private Response status(boolean up) {
        return Response.status(up ? 200 : 503).entity(Map.of("status", up ? "UP" : "DOWN")).build();
    }
}
