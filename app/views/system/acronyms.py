"""Acronyms & Glossary — AI and data centre terms used across this dashboard."""

import streamlit as st

st.title("Acronyms & Glossary")
st.caption("Definitions for AI, data centre, energy, and finance terms used across this dashboard.")

SECTIONS = {
    "AI Benchmarks": [
        ("GPQA", "Graduate-Level Google-Proof Q&A", "A benchmark of 448 expert-level science questions (physics, chemistry, biology) designed so that even a PhD researcher can only answer ~65% correctly. Tests genuine deep reasoning, not retrievable facts."),
        ("GPQA Diamond", "GPQA Diamond subset", "The hardest 198 questions from GPQA, used as the primary frontier model comparison point. Current SOTA is ~94%."),
        ("SWE-Bench", "Software Engineering Benchmark", "448 real GitHub issues from open-source repos. A model must autonomously read the codebase, understand the bug, and submit a passing patch. Tests end-to-end agentic software engineering."),
        ("SWE-Bench Verified", "SWE-Bench Verified subset", "A human-verified subset of 500 SWE-Bench tasks confirmed to be solvable and unambiguous. The standard comparison point for coding agents."),
        ("HLE", "Humanity's Last Exam", "~3,000 questions contributed by domain experts, designed to be the last benchmark humans can reliably beat frontier AI on. Current SOTA ~53%."),
        ("AIME", "American Invitational Mathematics Examination", "A prestigious high-school math competition. AIME 2025 refers to the 2025 paper used to test frontier model mathematical reasoning. Scores are % of problems solved."),
        ("MMLU", "Massive Multitask Language Understanding", "57-subject multiple-choice exam spanning humanities, STEM, and professional domains. Largely saturated above 90% for frontier models; MMLU-Pro is the harder successor."),
        ("MMLU-Pro", "MMLU Professional", "Harder variant of MMLU with 10-option MCQ and expert-level questions. Current frontier ~84-86%."),
        ("MMMLU", "Multilingual MMLU", "MMLU translated into 14 languages. Tests whether model knowledge transfers across languages."),
        ("ARC-AGI", "Abstract Reasoning Corpus for AGI", "Grid-based visual pattern completion tasks that require core knowledge and abstraction. Designed by François Chollet as a test of general intelligence."),
        ("SimpleQA", "Simple Factual QA", "Short factual questions with unambiguous, verifiable answers. Tests factual grounding and hallucination resistance."),
        ("BrowseComp", "Browser Comprehension", "Tasks requiring a model to navigate web pages and extract specific information. Tests agentic web interaction."),
        ("MRCR v2", "Multi-Round Conversation Reasoning v2", "Tests whether models can maintain accurate reasoning across long multi-turn conversations."),
        ("SciCode", "Scientific Coding", "Tasks requiring models to write correct scientific simulation and analysis code. Tests STEM + coding combined."),
        ("MCP Atlas", "Model Context Protocol Atlas", "Benchmark testing models' ability to use MCP tools correctly across complex agent workflows."),
        ("OSWorld", "Operating System World", "Tasks requiring models to operate desktop applications autonomously — file management, browser, terminal."),
        ("Terminal Bench", "Terminal Benchmark", "Tasks executed entirely in a terminal environment. Tests command-line proficiency and shell scripting."),
        ("Toolathlon", "Tool Marathon", "Multi-step tasks requiring sequential use of many different tools. Tests long-horizon agentic planning."),
    ],
    "AI Architecture & Training": [
        ("LLM", "Large Language Model", "A neural network trained on large text corpora to predict and generate language. GPT-4, Claude, Gemini are LLMs."),
        ("MoE", "Mixture of Experts", "An architecture where each forward pass only activates a subset of the model's parameters (the 'experts'). Allows large parameter counts at lower compute cost per token. Used in GPT-4, Mixtral, Grok."),
        ("RLHF", "Reinforcement Learning from Human Feedback", "Training technique where human raters score model outputs, and the model is trained to maximise those scores. Key to making models helpful and safe."),
        ("SFT", "Supervised Fine-Tuning", "Training a pre-trained model on labelled examples of desired behaviour. First step before RLHF."),
        ("CoT", "Chain of Thought", "Prompting or training technique that encourages models to reason step-by-step before giving a final answer. Significantly improves performance on multi-step problems."),
        ("RAG", "Retrieval-Augmented Generation", "A system that retrieves relevant documents from a knowledge base and injects them into the model's context before generating a response. Reduces hallucination on factual queries."),
        ("VLM", "Vision-Language Model", "An LLM that can also process image inputs alongside text. GPT-4o, Gemini, Claude 3+ are VLMs."),
        ("MCP", "Model Context Protocol", "An open protocol (Anthropic, 2024) for connecting AI models to external tools, data sources, and services in a standardised way."),
        ("SOTA", "State of the Art", "The current best-known result on a given benchmark or task. 'New SOTA' means a model has beaten the previous best score."),
        ("PUE", "Power Usage Effectiveness", "Ratio of total data centre power draw to IT equipment power draw. PUE = 1.0 is perfect efficiency; typical modern DCs are 1.2–1.4. Lower is better."),
        ("WUE", "Water Usage Effectiveness", "Litres of water consumed per kWh of IT load. Used to measure cooling water consumption in data centres. Lower is better."),
        ("TTFT", "Time to First Token", "Latency from sending a request to receiving the first generated token. Key UX metric for interactive applications."),
        ("Tok/s", "Tokens per second", "Throughput metric for language model inference. Higher = faster generation."),
    ],
    "Data Centre & Infrastructure": [
        ("DC", "Data Centre", "A facility housing computing servers, storage, and networking equipment. In this dashboard, specifically refers to hyperscale and colocation facilities."),
        ("HPC", "High Performance Computing", "Compute clusters optimised for scientific simulation, AI training, and research. Distinguished from general cloud computing by specialised networking (InfiniBand) and parallel workloads."),
        ("GPU", "Graphics Processing Unit", "Originally designed for rendering, now the dominant chip for AI model training and inference. NVIDIA's H100/B100/GB200 are the current frontier AI GPUs."),
        ("TPU", "Tensor Processing Unit", "Google's proprietary AI accelerator chip, used internally for training and serving Gemini models."),
        ("MW", "Megawatt", "Unit of power. 1 MW = 1,000 kW. Data centre capacity is measured in MW of IT load. A hyperscale campus can be 100–1,000 MW."),
        ("GW", "Gigawatt", "1,000 MW. Used for country-scale data centre demand estimates."),
        ("TWh", "Terawatt-hour", "Unit of energy = 1 trillion watt-hours. Used for annual electricity consumption. 1 TWh ≈ 114 MW average continuous load."),
        ("PPA", "Power Purchase Agreement", "A long-term contract to buy electricity at a fixed price, often from a renewable generator. Used by hyperscalers to secure cheap, clean power for data centres."),
        ("REIT", "Real Estate Investment Trust", "A company that owns income-producing real estate and distributes most profits to shareholders. DigiCo Infrastructure REIT, Equinix, and Digital Realty are listed REITs in the DC sector."),
        ("Colo", "Colocation", "A data centre that rents out space, power, and cooling to multiple tenants who bring their own servers. Different from a hyperscaler DC which is wholly owned and operated by one company."),
        ("Hyperscaler", "Hyperscale Cloud Provider", "Very large cloud operators (AWS, Azure, Google Cloud, Meta, Oracle) that build and operate massive proprietary data centres to run their own platforms."),
    ],
    "Australian Energy & Electricity": [
        ("NEM", "National Electricity Market", "Australia's interconnected electricity grid connecting Queensland, NSW, ACT, Victoria, South Australia, and Tasmania. Managed by AEMO."),
        ("AEMO", "Australian Energy Market Operator", "The independent body that manages the NEM and the WEM. Publishes demand forecasts, dispatch data, and capacity information."),
        ("NSW1", "NEM Region — New South Wales", "NSW and ACT NEM dispatch region. Sydney, Canberra, and surrounds."),
        ("VIC1", "NEM Region — Victoria", "Victoria NEM dispatch region. Melbourne and surrounds."),
        ("QLD1", "NEM Region — Queensland", "Queensland NEM dispatch region. Brisbane and surrounds."),
        ("SA1", "NEM Region — South Australia", "South Australia NEM dispatch region. Adelaide and surrounds."),
        ("TAS1", "NEM Region — Tasmania", "Tasmania NEM dispatch region. Connected to mainland via Basslink HVDC cable."),
        ("WA", "Western Australia (SWIS)", "Western Australia's South West Interconnected System — separate from the NEM, managed by the Western Australian Energy Market Operator (AEMO WA)."),
        ("MLF", "Marginal Loss Factor", "A coefficient applied to a generator's output to account for transmission losses. An MLF of 0.95 means 5% of generated power is lost before reaching the reference node."),
        ("IASR", "Integrated System Plan Assumptions and Scenarios Report", "AEMO's annual publication setting out energy demand scenarios used for the ISP (Integrated System Plan) modelling."),
        ("ESOO", "Electricity Statement of Opportunities", "AEMO's annual report assessing reliability of electricity supply across the NEM over a 10-year outlook horizon."),
        ("FCAS", "Frequency Control Ancillary Services", "Services that maintain power system frequency at 50 Hz. Batteries and fast-response generators provide FCAS and earn ancillary income."),
    ],
    "Finance & Investment": [
        ("CAPEX", "Capital Expenditure", "Spending on physical assets — data centre construction, servers, land. Hyperscaler CAPEX is the primary signal of AI infrastructure investment intensity."),
        ("OPEX", "Operating Expenditure", "Ongoing costs to run a business — staff, electricity, maintenance. Distinguished from one-off CAPEX."),
        ("EBITDA", "Earnings Before Interest, Taxes, Depreciation and Amortisation", "A proxy for operating cash flow. Commonly used to value infrastructure companies."),
        ("EV/EBITDA", "Enterprise Value / EBITDA", "Valuation multiple. A higher EV/EBITDA implies the market expects strong future growth or pricing power."),
        ("P/E", "Price-to-Earnings Ratio", "Share price divided by earnings per share. A measure of how expensive a stock is relative to current profits."),
        ("ASX", "Australian Securities Exchange", "Australia's primary stock exchange. ASX-listed companies relevant here: NEXTDC (NXT), Macquarie Technology Group (MAQ), DigiCo REIT (DGT), AUCloud (AUC), DXN (DXN)."),
        ("ESG", "Environmental, Social and Governance", "Non-financial reporting criteria used by investors. Data centres are ESG-sensitive due to energy consumption (E), supply chain (S), and board diversity (G)."),
        ("ASD", "Australian Signals Directorate", "Australia's signals intelligence and cybersecurity agency. ASD Certified cloud services (Protected, Strategic) are required for sensitive government workloads. Vault Cloud, AUCloud, Sliced Tech hold ASD certifications."),
    ],
    "Leaderboard Metrics (this dashboard)": [
        ("Code Arena", "Code Arena Composite Score", "llm-stats.com's composite ranking metric. Computed from a weighted combination of benchmark subscores (reasoning, math, coding, search, writing, vision, tools, etc.). Used as the primary sort key in the LLM Leaderboard table on this page."),
        ("Elo", "Elo Rating", "Originally a chess rating system. In AI context, refers to LMSYS Chatbot Arena Elo — computed from millions of blind human head-to-head comparisons between models. Higher Elo = more preferred by humans."),
        ("Composite Score (this dashboard)", "Mean benchmark score", "In the Leaderboard table on this page, 'Score' refers to the mean of GPQA, SWE-Bench Verified, HLE, and AIME-2025 scores (each as a percentage). A simple proxy for overall frontier capability."),
    ],
}

for section, terms in SECTIONS.items():
    st.subheader(section)
    rows = []
    for acronym, full, definition in terms:
        rows.append({
            "Acronym": acronym,
            "Full Name": full,
            "Definition": definition,
        })
    import pandas as pd
    df = pd.DataFrame(rows)
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Acronym": st.column_config.TextColumn(width="small"),
            "Full Name": st.column_config.TextColumn(width="medium"),
            "Definition": st.column_config.TextColumn(width="large"),
        },
    )
    st.markdown("")
