export interface HostMessages {
  commandNotFound: string;
  allContexts: string;
  chooseDatabase: string;
  activeMemory: (file: string) => string;
  newContext: string;
  moveFrom: (context: string) => string;
  targetContextName: string;
  purgePrompt: (id: number) => string;
  purgeAction: string;
  backupCreated: string;
  logDisabled: string;
  graphWoven: (links: number) => string;
  panelTitle: string;
  statusTooltip: string;
}

const MESSAGES: Record<"en" | "es", HostMessages> = {
  en: {
    commandNotFound: "Couldn't find 'hipercampo' or 'python -m hipercampo.cli'. "
      + "Install it with 'pip install --pre hipercampo', or set its path in "
      + "hipercampo.command.",
    allContexts: "all contexts",
    chooseDatabase: "Choose hipercampo database",
    activeMemory: (file) => `Active memory: ${file}`,
    newContext: "+ new context…",
    moveFrom: (context) => `Move from context “${context}” to…`,
    targetContextName: "Target context name",
    purgePrompt: (id) => `Delete memory #${id} for good? This is physical and `
      + "irreversible (unlike forgetting, which only makes it dormant).",
    purgeAction: "Delete for good",
    backupCreated: "Backup created.",
    logDisabled: "The log is disabled (HIPERCAMPO_LOG=0): there is no file to open.",
    graphWoven: (links) => `Graph woven: ${links} new links on the map.`,
    panelTitle: "hipercampo — memory",
    statusTooltip: "Hipercampo: view memories",
  },
  es: {
    commandNotFound: "No se encontró 'hipercampo' ni 'python -m hipercampo.cli'. "
      + "Instálalo con 'pip install --pre hipercampo' o configura su ruta en "
      + "hipercampo.command.",
    allContexts: "todos los contextos",
    chooseDatabase: "Elegir base de datos de hipercampo",
    activeMemory: (file) => `Memoria activa: ${file}`,
    newContext: "+ nuevo contexto…",
    moveFrom: (context) => `Mover del contexto «${context}» a…`,
    targetContextName: "Nombre del contexto destino",
    purgePrompt: (id) => `¿Borrar del todo el recuerdo #${id}? Es físico e `
      + "irreversible (a diferencia del olvido, que solo lo adormece).",
    purgeAction: "Borrar del todo",
    backupCreated: "Copia creada.",
    logDisabled: "El registro está desactivado (HIPERCAMPO_LOG=0): no hay fichero que abrir.",
    graphWoven: (links) => `Grafo tejido: ${links} enlaces nuevos en el mapa.`,
    panelTitle: "hipercampo — memoria",
    statusTooltip: "Hipercampo: ver memorias",
  },
};

export function hostMessages(language: string): HostMessages {
  return language.toLowerCase().startsWith("es") ? MESSAGES.es : MESSAGES.en;
}
