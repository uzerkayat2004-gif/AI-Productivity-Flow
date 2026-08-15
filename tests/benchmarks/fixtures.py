"""Video Flow Standard Benchmark Fixtures.

A curated dataset of 12 diverse domain sources used to benchmark Video Flow
scene planning, explanation quality, factual grounding, and hybrid render routing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BenchmarkSample:
    id: str
    domain: str
    title: str
    source_text: str
    expected_key_concepts: list[str]
    expected_claims_count: int
    recommended_min_scenes: int
    recommended_max_scenes: int
    complexity: str  # "introductory", "intermediate", "advanced"
    metadata: dict[str, Any] = field(default_factory=dict)


BENCHMARK_FIXTURES: list[BenchmarkSample] = [
    BenchmarkSample(
        id="bench_01_science_crispr",
        domain="Science & Biotechnology",
        title="How CRISPR-Cas9 Gene Editing Works",
        source_text=(
            "CRISPR-Cas9 is a revolutionary genome editing technology adapted from a bacterial defense system. "
            "It consists of two key components: the Cas9 enzyme, which acts as molecular scissors to cut DNA, "
            "and a guide RNA (gRNA), which directs Cas9 to a specific sequence of nucleotides in the target genome. "
            "Once Cas9 introduces a double-strand break at the target site, the cell's natural DNA repair machinery "
            "takes over, enabling targeted gene knockout, insertion, or correction."
        ),
        expected_key_concepts=["Cas9 enzyme", "Guide RNA", "Double-strand break", "DNA repair"],
        expected_claims_count=4,
        recommended_min_scenes=3,
        recommended_max_scenes=6,
        complexity="intermediate",
    ),
    BenchmarkSample(
        id="bench_02_tech_git_branching",
        domain="Software Engineering",
        title="Understanding Git Branching and Merging",
        source_text=(
            "Git is a distributed version control system that models history as a directed acyclic graph of commits. "
            "A branch in Git is simply a lightweight movable pointer to a commit. Creating a new branch does not duplicate files; "
            "it only creates a new reference. When merging, Git uses either a fast-forward merge (if no diverging commits exist) "
            "or creates a 3-way merge commit combining two distinct divergent histories."
        ),
        expected_key_concepts=["Directed acyclic graph", "Movable pointer", "Fast-forward merge", "3-way merge"],
        expected_claims_count=4,
        recommended_min_scenes=3,
        recommended_max_scenes=6,
        complexity="intermediate",
    ),
    BenchmarkSample(
        id="bench_03_abstract_quantum",
        domain="Physics & Abstract Concepts",
        title="Quantum Superposition and Entanglement Explained",
        source_text=(
            "Quantum superposition is the fundamental principle where a quantum system can exist in a linear combination of multiple states "
            "simultaneously until a measurement is performed, causing wave function collapse. "
            "Quantum entanglement occurs when two or more particles become correlated such that the quantum state of each particle "
            "cannot be described independently of the state of the others, regardless of the spatial distance separating them."
        ),
        expected_key_concepts=["Superposition", "Wave function collapse", "Entanglement", "State correlation"],
        expected_claims_count=3,
        recommended_min_scenes=3,
        recommended_max_scenes=5,
        complexity="advanced",
    ),
    BenchmarkSample(
        id="bench_04_finance_compound_interest",
        domain="Finance & Economics",
        title="The Power of Compound Interest",
        source_text=(
            "Compound interest is interest calculated on the initial principal and on the accumulated interest of previous periods. "
            "Expressed by the formula A = P(1 + r/n)^(nt), compounding creates exponential rather than linear wealth growth over time. "
            "The frequency of compounding intervals—monthly, daily, or continuously—directly accelerates growth, making the time horizon "
            "the most powerful variable in wealth accumulation."
        ),
        expected_key_concepts=["Principal", "Accumulated interest", "Exponential growth", "Compounding frequency"],
        expected_claims_count=3,
        recommended_min_scenes=3,
        recommended_max_scenes=5,
        complexity="introductory",
    ),
    BenchmarkSample(
        id="bench_05_history_silk_road",
        domain="History & Geopolitics",
        title="The Silk Road: Ancient Globalization",
        source_text=(
            "The Silk Road was an expansive network of Eurasian trade routes active from the Han Dynasty (130 BCE) until the Ottoman Empire "
            "boycotted trade in 1453. Beyond luxury commodities like Chinese silk, porcelain, Roman glassware, and spices, "
            "the routes catalyzed the transfer of technologies (papermaking, gunpowder), philosophies (Buddhism, Islam), and pathogens (the Black Death)."
        ),
        expected_key_concepts=["Eurasian trade routes", "Commodity exchange", "Technology transfer", "Cultural diffusion"],
        expected_claims_count=3,
        recommended_min_scenes=3,
        recommended_max_scenes=5,
        complexity="introductory",
    ),
    BenchmarkSample(
        id="bench_06_tech_rest_vs_graphql",
        domain="Software Architecture",
        title="REST APIs vs GraphQL: Architectural Trade-Offs",
        source_text=(
            "REST is an architectural style based on standardized HTTP verbs and fixed endpoint resources, often leading to over-fetching "
            "or under-fetching of data across multiple network roundtrips. "
            "GraphQL is a query language and runtime with a single endpoint where clients request exactly the fields they need, "
            "preventing over-fetching at the cost of increased server-side query complexity and caching challenges."
        ),
        expected_key_concepts=["HTTP verbs & endpoints", "Over-fetching & under-fetching", "GraphQL query language", "Caching trade-offs"],
        expected_claims_count=4,
        recommended_min_scenes=3,
        recommended_max_scenes=6,
        complexity="intermediate",
    ),
    BenchmarkSample(
        id="bench_07_science_photosynthesis",
        domain="Biology & Environmental Science",
        title="The Two Stages of Photosynthesis",
        source_text=(
            "Photosynthesis converts light energy into chemical energy in plants and algae through two interconnected stages. "
            "First, light-dependent reactions in the thylakoid membrane absorb photons to split water molecules (H2O), releasing oxygen (O2) "
            "and generating ATP and NADPH. Second, the light-independent Calvin cycle in the stroma uses ATP and NADPH to fix carbon dioxide (CO2) into glucose."
        ),
        expected_key_concepts=["Light-dependent reactions", "Thylakoid membrane", "Calvin cycle", "ATP & NADPH", "Carbon fixation"],
        expected_claims_count=4,
        recommended_min_scenes=3,
        recommended_max_scenes=5,
        complexity="intermediate",
    ),
    BenchmarkSample(
        id="bench_08_saas_churn_metrics",
        domain="Business & Data Analytics",
        title="SaaS Unit Economics: Churn, LTV, and CAC",
        source_text=(
            "In SaaS business models, customer churn rate measures the percentage of subscribers who cancel within a given timeframe. "
            "Customer Lifetime Value (LTV) represents the total gross profit generated per account, calculated as ARPU divided by churn rate. "
            "A sustainable SaaS unit economic engine typically requires an LTV to Customer Acquisition Cost (CAC) ratio of 3:1 or higher, "
            "with a CAC payback period under 12 months."
        ),
        expected_key_concepts=["Churn rate", "Customer Lifetime Value (LTV)", "Customer Acquisition Cost (CAC)", "LTV:CAC Ratio"],
        expected_claims_count=4,
        recommended_min_scenes=3,
        recommended_max_scenes=6,
        complexity="intermediate",
    ),
    BenchmarkSample(
        id="bench_09_arch_microservices_vs_monolith",
        domain="Cloud Computing & Distributed Systems",
        title="Microservices vs Modular Monolith",
        source_text=(
            "Monolithic architecture bundles all application components into a single deployable artifact, maximizing runtime performance, "
            "simplicity of transactional consistency, and developer velocity early in a project's lifecycle. "
            "Microservices partition a system into independently deployable, domain-isolated services communicating via network protocols, "
            "enabling organizational scalability at the expense of distributed tracing, network latency, and eventual consistency complexity."
        ),
        expected_key_concepts=["Monolith simplicity", "Microservice domain isolation", "Network latency", "Eventual consistency"],
        expected_claims_count=4,
        recommended_min_scenes=3,
        recommended_max_scenes=6,
        complexity="advanced",
    ),
    BenchmarkSample(
        id="bench_10_algorithms_quicksort",
        domain="Computer Science & Algorithms",
        title="Quicksort: Divide and Conquer in Action",
        source_text=(
            "Quicksort is an efficient, in-place divide-and-conquer comparison sorting algorithm. "
            "It works by selecting a 'pivot' element from the array and partitioning the remaining elements into two sub-arrays: "
            "those less than the pivot and those greater than the pivot. The sub-arrays are then sorted recursively. "
            "Quicksort averages O(n log n) time complexity, with worst-case O(n^2) when poor pivot selection occurs on already sorted data."
        ),
        expected_key_concepts=["Divide and conquer", "Pivot selection", "Partitioning", "O(n log n) complexity"],
        expected_claims_count=4,
        recommended_min_scenes=3,
        recommended_max_scenes=5,
        complexity="intermediate",
    ),
    BenchmarkSample(
        id="bench_11_economics_inflation_interest",
        domain="Economics & Macro Policy",
        title="How Central Banks Use Interest Rates to Control Inflation",
        source_text=(
            "Inflation represents the general increase in prices and fall in the purchasing power of money over time. "
            "Central banks adjust the benchmark policy interest rate to manage inflation. Raising interest rates increases the cost of borrowing, "
            "dampening consumer spending and business investment, which cools aggregate demand and slows price growth. "
            "Conversely, lowering interest rates stimulates economic expansion by reducing the cost of credit."
        ),
        expected_key_concepts=["Inflation & purchasing power", "Benchmark interest rate", "Cost of borrowing", "Aggregate demand"],
        expected_claims_count=4,
        recommended_min_scenes=3,
        recommended_max_scenes=5,
        complexity="introductory",
    ),
    BenchmarkSample(
        id="bench_12_medicine_mrna_vaccines",
        domain="Medicine & Immunology",
        title="How mRNA Vaccines Teach the Immune System",
        source_text=(
            "mRNA vaccines deliver synthetic messenger RNA lipid nanoparticles into human cells. "
            "The mRNA instructs ribosomes to temporarily manufacture a harmless viral antigen (such as the SARS-CoV-2 spike protein). "
            "The immune system recognizes this foreign protein, prompting B cells to produce neutralizing antibodies and activating T cells. "
            "The synthetic mRNA is naturally degraded within hours without entering the cell nucleus or altering the host genome."
        ),
        expected_key_concepts=["Lipid nanoparticles", "Ribosome translation", "Antigen production", "Antibody & T cell response", "mRNA degradation"],
        expected_claims_count=4,
        recommended_min_scenes=3,
        recommended_max_scenes=6,
        complexity="intermediate",
    ),
]
