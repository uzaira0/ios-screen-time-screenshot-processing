interface ImportMetaEnv {
  readonly MODE: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

// Non-standard HTML attributes for folder selection
declare namespace React {
  interface InputHTMLAttributes<T> {
    webkitdirectory?: string;
    directory?: string;
  }
}
