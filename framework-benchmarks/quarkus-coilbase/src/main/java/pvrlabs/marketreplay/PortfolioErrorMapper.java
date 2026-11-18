package pvrlabs.marketreplay;

import jakarta.ws.rs.WebApplicationException;
import jakarta.ws.rs.core.Response;
import jakarta.ws.rs.ext.ExceptionMapper;
import jakarta.ws.rs.ext.Provider;

import java.util.Map;

@Provider
public class PortfolioErrorMapper implements ExceptionMapper<RuntimeException> {
    private static final org.jboss.logging.Logger LOG =
            org.jboss.logging.Logger.getLogger(PortfolioErrorMapper.class);

    @Override
    public Response toResponse(RuntimeException e) {
        int status;
        if (e instanceof InvalidHoldingException) {
            status = 400;
        } else if (e instanceof UserNotFoundException) {
            status = 404;
        } else if (e instanceof MarketPricesUnavailableException) {
            status = 503;
        } else if (e instanceof WebApplicationException webException) {
            status = webException.getResponse().getStatus();
        } else {
            status = 500;
        }
        String detail = e.getMessage() == null ? "Request failed" : e.getMessage();
        if (status >= 500 && !(e instanceof MarketPricesUnavailableException)) {
            LOG.error("Unexpected Portfolio request failure", e);
            detail = "Internal server error";
        }
        return Response.status(status)
                .type("application/problem+json")
                .entity(Map.of("status", status, "detail", detail))
                .build();
    }
}
