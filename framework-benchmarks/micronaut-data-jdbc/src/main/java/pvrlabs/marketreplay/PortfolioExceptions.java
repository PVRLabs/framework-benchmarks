package pvrlabs.marketreplay;

class InvalidHoldingException extends RuntimeException {
    InvalidHoldingException() {
        super("Expected supported symbol and quantity 0 <= q < 10^13 with at most 6 decimals");
    }
}

class UserNotFoundException extends RuntimeException {
    UserNotFoundException() {
        super("User not found");
    }
}

class MarketPricesUnavailableException extends RuntimeException {
    MarketPricesUnavailableException() {
        super("Market prices unavailable");
    }
}
