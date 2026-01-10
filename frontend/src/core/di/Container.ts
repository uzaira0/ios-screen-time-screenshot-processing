type Factory<T> = () => T;
type ServiceImplementation<T> = T | Factory<T>;

export class ServiceContainer {
  private services = new Map<string, ServiceImplementation<any>>();
  private singletons = new Map<string, any>();

  register<T>(token: string, implementation: T): void {
    this.services.set(token, implementation);
  }

  registerFactory<T>(token: string, factory: Factory<T>): void {
    this.services.set(token, factory);
  }

  registerSingleton<T>(token: string, implementation: T | Factory<T>): void {
    this.services.set(token, implementation);

    if (typeof implementation !== "function") {
      this.singletons.set(token, implementation);
    }
  }

  resolve<T>(token: string): T {
    if (this.singletons.has(token)) {
      return this.singletons.get(token) as T;
    }

    const implementation = this.services.get(token);

    if (!implementation) {
      throw new Error(`Service not registered: ${token}`);
    }

    if (typeof implementation === "function") {
      const instance = (implementation as Factory<T>)();

      if (this.services.get(token) === implementation) {
        const serviceEntry = this.services.get(token);
        if (serviceEntry && typeof serviceEntry === "function") {
          this.singletons.set(token, instance);
        }
      }

      return instance;
    }

    return implementation as T;
  }

  has(token: string): boolean {
    return this.services.has(token);
  }

  clear(): void {
    this.services.clear();
    this.singletons.clear();
  }

  /**
   * Destroy all services that have a terminate/destroy method.
   * This should be called when the app unmounts to clean up resources.
   */
  destroy(): void {
    // Call terminate/destroy on all singleton instances
    for (const [token, instance] of this.singletons.entries()) {
      if (instance && typeof instance === "object") {
        // Check for common cleanup method names
        if (
          "terminate" in instance &&
          typeof instance.terminate === "function"
        ) {
          try {
            instance.terminate();
          } catch (error) {
            console.error(
              `[ServiceContainer] Error terminating ${token}:`,
              error,
            );
          }
        } else if (
          "destroy" in instance &&
          typeof instance.destroy === "function"
        ) {
          try {
            instance.destroy();
          } catch (error) {
            console.error(
              `[ServiceContainer] Error destroying ${token}:`,
              error,
            );
          }
        } else if (
          "cleanup" in instance &&
          typeof instance.cleanup === "function"
        ) {
          try {
            instance.cleanup();
          } catch (error) {
            console.error(
              `[ServiceContainer] Error cleaning up ${token}:`,
              error,
            );
          }
        }
      }
    }

    this.clear();
  }
}
