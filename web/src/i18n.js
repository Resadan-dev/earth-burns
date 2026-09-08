/**
 * Language dictionary and persistence.
 *
 * English is the default for every first-time visitor, regardless of browser
 * language: the switch is manual, and only a saved choice from a previous
 * visit changes that. Every user-facing string in the app lives here, so a
 * language switch is one function rebuilding the DOM from this data rather
 * than scattered text edits across the page.
 */

export const DEFAULT_LANG = "en";
const STORAGE_KEY = "earthburns-lang";

const EN = {
  mapAria: "World map of extreme fire weather",
  boot: "Loading 46 years of fire weather",
  standfirst: "Where human-caused warming has made wildfire weather more " +
    "dangerous, 1979-2024. Found by comparing the planet we have with one " +
    "where that warming never happened.",
  aboutAria: "What is this?",
  close: "Close",
  monthSliderAria: "Month in the record",
  loadingDecade: "Loading this decade",
  play: "Play",
  pause: "Pause",
  caption: "Share of burnable land in extreme fire weather",
  figures: { obs: "Our world", cf: "Without warming", gap: "Gap" },
  twin: { top: "Our world", bottom: "Without human-caused warming" },
  legend: {
    calm: "calm",
    extreme: "every day extreme",
    diffLow: "fewer extreme days than without warming",
    diffHigh: "more",
  },
  modes: { 0: "Our world", 1: "Without warming", 3: "Side by side", 2: "The human fingerprint" },
  navSecondary: "The building blocks",
  keyNumbers: {
    trigger: "The numbers",
    title: "The headline numbers",
    note: "From this dataset, and the wider published research it builds on.",
    stats: [
      { value: "2×", caption: "Widespread extreme fire weather has more than " +
        "doubled across most of the world since 1979." },
      { value: ">50%", caption: "of that increase is linked to human-caused " +
        "climate change, not natural swings." },
      { value: "15×", caption: "More days of synchronised extreme fire weather " +
        "in southern South America now than in the 1980s." },
      { value: "+8.5 days", caption: "More extreme fire-weather days each " +
        "year, per place, than in a world without warming." },
      { value: "+60%", caption: "Rise in global forest-fire carbon emissions " +
        "between 2001 and 2023." },
    ],
  },
  modeHelpAria(label) { return `What does "${label}" show?`; },
  modeHelp: {
    0: {
      title: "Our world",
      body: "The Fire Weather Index calculated from real weather, 1979-2024. " +
        "Colour marks the days each month with unusually dangerous fire conditions " +
        "for that place: heat, dryness and wind combined. This is what actually happened.",
    },
    1: {
      title: "Without human-caused warming",
      body: "The same calculation, run on weather with the human-caused warming " +
        "signal removed. Temperature, humidity, wind and rainfall are adjusted using " +
        "the average response of 20 climate models. It estimates the fire weather " +
        "this planet would have seen without our emissions.",
    },
    3: {
      title: "Side by side",
      body: "Both maps at once, our world above and the world without warming " +
        "below. The difference in intensity is visible directly, without " +
        "switching back and forth between the two.",
    },
    2: {
      title: "The human fingerprint",
      body: "Our world minus the world without human-caused warming, cell by " +
        "cell. Both share the same natural weather variability, so only that " +
        "warming differs between them. Red means more extreme fire-weather " +
        "days because of it. Blue means fewer, which happens in a few " +
        "regions, mostly through changes in rainfall.",
    },
  },
  aboutHelp: {
    title: "What am I looking at?",
    facts: [
      {
        term: "What it shows",
        detail: "How dangerous the weather is for wildfires each month, not " +
          "whether a fire actually happened: heat, dryness and wind combined " +
          "into a single score, compared to what is normal for that exact place.",
      },
      {
        term: "Human role",
        detail: "Both worlds rise over the decades from natural variability " +
          "alone. But scientists who built this dataset found that more than " +
          "half of the global increase in widespread extreme fire weather " +
          "since 1979 is linked to human-caused climate change.",
      },
      {
        term: "Source",
        detail: "Calculated from ERA5 weather data by climate scientists and " +
          "published as open research data, covering 1979 to 2024.",
      },
      {
        term: "Coverage",
        detail: "Only burnable land is shown, such as forests, shrubland and " +
          "grassland. Ocean, ice, desert, cropland and cities stay dark.",
      },
      {
        term: "Resolution",
        detail: "Each cell on the map is about 28km across, roughly the width " +
          "of a large city. There are about 185,000 of them. Each frame is one " +
          "month, built from that month's daily values.",
      },
    ],
    links: [
      { label: "Read the study", href: "https://doi.org/10.1126/sciadv.adx8813" },
      { label: "Get the data", href: "https://doi.org/10.5061/dryad.cfxpnvxkp" },
    ],
  },
  months: ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"],
};

const FR = {
  mapAria: "Carte mondiale de la météo extrême propice aux incendies",
  boot: "Chargement de 46 ans de météo du feu",
  standfirst: "Là où le réchauffement d'origine humaine a rendu la météo du " +
    "feu plus dangereuse, 1979-2024. Trouvé en comparant la planète que nous " +
    "avons avec une planète où ce réchauffement n'aurait jamais eu lieu.",
  aboutAria: "Qu'est-ce que c'est ?",
  close: "Fermer",
  monthSliderAria: "Mois de la période",
  loadingDecade: "Chargement de cette décennie",
  play: "Lecture",
  pause: "Pause",
  caption: "Part des terres brûlables en météo extrême",
  figures: { obs: "Notre monde", cf: "Sans réchauffement", gap: "Écart" },
  twin: { top: "Notre monde", bottom: "Sans réchauffement d'origine humaine" },
  legend: {
    calm: "calme",
    extreme: "extrême tous les jours",
    diffLow: "moins de jours extrêmes que sans réchauffement",
    diffHigh: "plus",
  },
  modes: { 0: "Notre monde", 1: "Sans réchauffement", 3: "Côte à côte", 2: "L'empreinte humaine" },
  navSecondary: "Les briques de base",
  keyNumbers: {
    trigger: "Les chiffres",
    title: "Les chiffres à retenir",
    note: "Issus de ce jeu de données et des recherches publiées sur lesquelles il s'appuie.",
    stats: [
      { value: "2×", caption: "La météo extrême généralisée a plus que " +
        "doublé dans la plupart du monde depuis 1979." },
      { value: ">50%", caption: "de cette hausse est liée au changement " +
        "climatique d'origine humaine, pas aux variations naturelles." },
      { value: "15×", caption: "Plus de jours de météo extrême synchronisée " +
        "en Amérique du Sud australe aujourd'hui que dans les années 1980." },
      { value: "+8,5 jours", caption: "Jours de météo extrême en plus chaque " +
        "année, au même endroit, par rapport à un monde sans réchauffement." },
      { value: "+60%", caption: "Hausse des émissions mondiales de carbone " +
        "dues aux feux de forêt entre 2001 et 2023." },
    ],
  },
  modeHelpAria(label) { return `Que montre « ${label} » ?`; },
  modeHelp: {
    0: {
      title: "Notre monde",
      body: "Le Fire Weather Index calculé à partir de la météo réelle, 1979-2024. " +
        "La couleur marque les jours de chaque mois où les conditions étaient " +
        "anormalement dangereuses pour le feu, à cet endroit précis : chaleur, " +
        "sécheresse et vent combinés. C'est ce qui s'est réellement passé.",
    },
    1: {
      title: "Sans réchauffement d'origine humaine",
      body: "Le même calcul, appliqué à une météo dont le signal de réchauffement " +
        "d'origine humaine a été retiré. Température, humidité, vent et " +
        "précipitations sont ajustés à partir de la réponse moyenne de 20 " +
        "modèles climatiques. Cela estime la météo du feu que cette planète " +
        "aurait connue sans nos émissions.",
    },
    3: {
      title: "Côte à côte",
      body: "Les deux cartes en même temps, notre monde au-dessus et le monde " +
        "sans réchauffement en dessous. L'écart d'intensité se voit directement, " +
        "sans devoir passer de l'une à l'autre.",
    },
    2: {
      title: "L'empreinte humaine",
      body: "Notre monde moins le monde sans réchauffement d'origine humaine, " +
        "cellule par cellule. Les deux partagent la même variabilité météo " +
        "naturelle, seul ce réchauffement diffère entre eux. Le rouge signifie " +
        "plus de jours de météo extrême à cause de lui. Le bleu en signifie " +
        "moins, ce qui arrive dans certaines régions, surtout " +
        "à cause de changements de précipitations.",
    },
  },
  aboutHelp: {
    title: "Qu'est-ce que je regarde ?",
    facts: [
      {
        term: "Ce que ça montre",
        detail: "À quel point la météo est dangereuse pour les feux de forêt " +
          "chaque mois, pas si un incendie a réellement eu lieu : chaleur, " +
          "sécheresse et vent combinés en un seul score, comparé à ce qui est " +
          "normal à cet endroit précis.",
      },
      {
        term: "Part humaine",
        detail: "Les deux mondes montent au fil des décennies, rien qu'avec la " +
          "variabilité naturelle. Mais les scientifiques à l'origine de ces " +
          "données ont établi que plus de la moitié de l'augmentation mondiale " +
          "de la météo extrême généralisée depuis 1979 est liée au changement " +
          "climatique d'origine humaine.",
      },
      {
        term: "Source",
        detail: "Calculé à partir des données météo ERA5 par des chercheurs en " +
          "climatologie, et publié en libre accès, sur la période 1979 à 2024.",
      },
      {
        term: "Couverture",
        detail: "Seules les terres brûlables sont représentées : forêts, " +
          "arbustes, prairies. Océans, glaces, déserts, cultures et villes " +
          "restent sombres.",
      },
      {
        term: "Résolution",
        detail: "Chaque cellule de la carte fait environ 28 km de large, à " +
          "peu près la largeur d'une grande ville. Il y en a environ 185 000. " +
          "Chaque image correspond à un mois, construite à partir de ses " +
          "valeurs quotidiennes.",
      },
    ],
    links: [
      { label: "Lire l'étude", href: "https://doi.org/10.1126/sciadv.adx8813" },
      { label: "Explorer les données", href: "https://doi.org/10.5061/dryad.cfxpnvxkp" },
    ],
  },
  months: ["JANV", "FÉVR", "MARS", "AVR", "MAI", "JUIN", "JUIL", "AOÛT", "SEPT", "OCT", "NOV", "DÉC"],
};

const STRINGS = { en: EN, fr: FR };

export function getInitialLang() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved && Object.hasOwn(STRINGS, saved)) return saved;
  } catch {
    // Private browsing or storage disabled: fall through to the default.
  }
  return DEFAULT_LANG;
}

export function saveLang(lang) {
  try {
    localStorage.setItem(STORAGE_KEY, lang);
  } catch {
    // Nothing to persist to; the choice still applies for this visit.
  }
}

export function t(lang) {
  return STRINGS[lang] || STRINGS[DEFAULT_LANG];
}
