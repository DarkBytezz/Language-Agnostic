document.addEventListener('DOMContentLoaded', function () {
    const modal = document.getElementById('courseModal');
    const modalTitle = document.getElementById('modalTitle');
    const modalDesc = document.getElementById('modalDesc');
    const modalElig = document.getElementById('modalElig');
    const modalDuration = document.getElementById('modalDuration');
    const modalAdm = document.getElementById('modalAdm');
    const modalFees = document.getElementById('modalFees');
    const closeBtn = document.querySelector('.modal-close');

    // Course data details for modal
    const courseDetails = {
        MBA: {
            description: "Master of Business Administration (General)",
            eligibility: "Bachelors (Recognized)",
            duration: "2 years",
            adm: "Apply through university entrance exam or merit-based selection.",
            fees: "Approx. $15,000 per year"
        },
        BBA: {
            description: "Bachelor of Business Administration (General)",
            eligibility: "+2 (Recognized)",
            duration: "3 years",
            adm: "Admission based on 10+2 marks or entrance test.",
            fees: "Approx. $8,000 per year"
        },
        MCA: {
            description: "Master of Computer Application",
            eligibility: "Bachelors (Recognized)",
            duration: "2 years",
            adm: "Through entrance exam and academic merit.",
            fees: "Approx. $12,000 per year"
        },
        BCA: {
            description: "Bachelor of Computer Application",
            eligibility: "+2 (Recognized)",
            duration: "3 years",
            adm: "Based on 10+2 academic qualification or entrance exam.",
            fees: "Approx. $7,000 per year"
        },
        MA: {
            description: "Master of Arts (English): Bachelor’s degree in English or related discipline. Minimum 50% aggregate marks (45% for SC/ST).",
            eligibility: "Bachelor’s degree in English or related discipline. Minimum 50% aggregate marks (45% for SC/ST).",
            duration: "2 years (4 Semesters)",
            adm: "Apply for CUCET (Chandigarh University Common Entrance Test). Selection based on CUCET score / merit. Scholarships available on CUCET score, academic merit, sports, NCC, defense quota.",
            fees: "Per Year Fee: ~₹70,000 – ₹85,000 Total (2 Years): ~₹1.4 – ₹1.7 lakh Exam Fee: ₹2,500 per year Security Deposit: ₹2,000"
        },
        BA: {
            description: "Bachelor of Arts (English)",
            eligibility: "Bachelors (Recognized)",
            duration: "3 years",
            adm: "Admission based on 10+2 marks or merit.",
            fees: "Approx. $6,000 per year"
        }
    };

    // Function to open and populate modal with course data
    function showModal(courseName) {
        const details = courseDetails[courseName];
        if (!details) return;

        modalTitle.textContent = courseName;
        modalDesc.textContent = details.description || "N/A";
        modalElig.textContent = details.eligibility || "N/A";
        modalDuration.textContent = details.duration || "N/A";
        modalAdm.textContent = details.adm || "N/A";
        modalFees.textContent = details.fees || "N/A";

        modal.style.display = 'block';
    }

    // Attach event listeners to "Know More" buttons
    document.querySelectorAll('.tile-btn').forEach(button => {
        button.addEventListener('click', (e) => {
            const courseTile = e.target.closest('.grid-tile');
            const courseName = courseTile.querySelector('.tile-main-title').textContent.trim();
            showModal(courseName);
        });
    });

    // Close modal on close button click
    closeBtn.addEventListener('click', () => {
        modal.style.display = 'none';
    });

    // Close modal by clicking outside modal content
    window.addEventListener('click', (event) => {
        if (event.target === modal) {
            modal.style.display = 'none';
        }
    });

    // Optional: close modal on ESC key press
    window.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && modal.style.display === 'block') {
            modal.style.display = 'none';
        }
    });
});
