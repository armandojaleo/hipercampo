export interface HostMessages {
  commandNotFound: string;
  noFolderOpen: string;
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
  statusValue: (saved: string) => string;
  valueTooltip: (served: number, injected: number, saved: number, today: number) => string;
  editLinkedPrompt: string;
  editLinkedPlaceholder: string;
  linkedUpdated: (value: string) => string;
}

const MESSAGES: Record<"en" | "es", HostMessages> = {
  en: {
    commandNotFound: "Couldn't find 'hipercampo' or 'python -m hipercampo.cli'. "
      + "Install it with 'pip install --pre hipercampo', or set its path in "
      + "hipercampo.command.",
    noFolderOpen: "Open a folder first: hipercampo is enabled per project.",
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
    panelTitle: "Hipercampo — memory",
    statusTooltip: "Hipercampo: view memories",
    statusValue: (saved) => `Hipercampo · ${saved} lean`,
    valueTooltip: (served, injected, saved, today) =>
      `Memory served ${served} times · ~${injected} tokens injected`
      + ` · ~${saved} kept lean by the budget · ${today} today.`
      + `\nEstimates (Claude's tokenizer isn't public). Click to open the viewer.`,
    editLinkedPrompt: "Linked contexts (HIPERCAMPO_LINKED)",
    editLinkedPlaceholder: "Empty = none, \"*\" = all, or \"proj-blog,proj-docs\"",
    linkedUpdated: (value) => value
      ? `Linked contexts updated: ${value}`
      : "Linked contexts cleared: this context no longer reads from others.",
  },
  es: {
    commandNotFound: "No se encontró 'hipercampo' ni 'python -m hipercampo.cli'. "
      + "Instálalo con 'pip install --pre hipercampo' o configura su ruta en "
      + "hipercampo.command.",
    noFolderOpen: "Abre antes una carpeta: hipercampo se activa por proyecto.",
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
    panelTitle: "Hipercampo — memoria",
    statusTooltip: "Hipercampo: ver memorias",
    statusValue: (saved) => `Hipercampo · ${saved} ahorrados`,
    valueTooltip: (served, injected, saved, today) =>
      `Memoria servida ${served} veces · ~${injected} tokens inyectados`
      + ` · ~${saved} recortados por el presupuesto · ${today} hoy.`
      + `\nEstimaciones (el tokenizador de Claude no es público). Clic para abrir el visor.`,
    editLinkedPrompt: "Contextos enlazados (HIPERCAMPO_LINKED)",
    editLinkedPlaceholder: "Vacío = ninguno, «*» = todos, o «proj-blog,proj-docs»",
    linkedUpdated: (value) => value
      ? `Contextos enlazados actualizados: ${value}`
      : "Contextos enlazados vaciados: este contexto ya no lee de otros.",
  },
};

export function hostMessages(language: string): HostMessages {
  return language.toLowerCase().startsWith("es") ? MESSAGES.es : MESSAGES.en;
}
