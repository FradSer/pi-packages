/**
 * The Bun surface the decision fixture uses.
 *
 * Bun runs the fixtures, but the repository installs no Bun type definitions
 * and its typecheck deliberately skips Bun-run fixtures. Declaring the exact
 * surface used keeps this package's own test typecheck meaningful without a new
 * dependency, and any other Bun API stays an error.
 */
declare const Bun: {
  serve(options: {
    port: number;
    fetch: (request: Request) => Response | Promise<Response>;
  }): {
    readonly port: number;
    stop(force?: boolean): void;
  };
};
