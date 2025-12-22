# STUDENT OPERATIONS — TASK SCHEDULE & ENDPOINT MAP

We will think in **learner journeys**, not CRUD.

---

## PHASE 0 — Preconditions (Already Done ✅)

These must be true before any student logic runs:

* Courses are **published=True**
* Modules & Lessons exist under Course
* MediaAsset linked to Lesson
* Admin uploads courses (for now)

Models already support all of this.

---

# PHASE 1 — DISCOVERY & ACCESS (Read-only, Public)

### 1. Browse Courses

**Endpoint**

```
GET /courses/
```

**Models involved**

* Course
* CourseCategory
* CourseTag
* CourseFeedback (optional aggregation)

**Rules**

* `published=True` only
* pagination
* category / tag filter
* search (basic first, SearchVector later)

**Outcome**
Learner can discover courses.

---

### 2. Course Detail Page

**Endpoint**

```
GET /courses/<slug>/
```

**Models**

* Course
* Module
* Lesson
* CourseFeedback (ratings)
* Announcement (optional)

**Rules**

* Public view allowed
* Show curriculum outline
* If authenticated → show enroll CTA or progress

**Outcome**
Learner understands course structure.

---

# PHASE 2 — ENROLLMENT & ACCESS CONTROL

### 3. Enroll in Course

**Endpoint**

```
POST /courses/<slug>/enroll/
```

**Models**

* Enrollment

**Rules**

* User must be authenticated
* `UniqueConstraint(learner, course)`
* Default status = active

**Side Effects**

* Initialize progress tracking (lazy or eager)

**Outcome**
Learner gains access to lessons.

---

### 4. Enrollment Gatekeeping (Middleware-level logic)

**Implicit rule applied everywhere**

* Lesson / quiz / assignment access requires:

  * Enrollment exists
  * Enrollment.status == active

This is not a view — it is a **shared guard**.

---

# PHASE 3 — LEARNING FLOW (Core LMS)

### 5. Module Detail

**Endpoint**

```
GET /modules/<course_slug>/<module_slug>/
```

**Models**

* Module
* Lesson
* Enrollment
* LearnerProgress

**Rules**

* Must be enrolled
* Lessons ordered by position
* Lock future lessons if you want (optional later)

**Outcome**
Learner navigates lessons.

---

### 6. Lesson View (Critical)

**Endpoint**

```
GET /lessons/<course_slug>/<module_slug>/<lesson_slug>/
```

**Models**

* Lesson
* MediaAsset
* LearnerProgress
* Enrollment

**Actions on access**

* Create or update LearnerProgress:

  * first_opened_at
  * started_at
* Render:

  * video / PDF / article

**Outcome**
Learner consumes content.

---

### 7. Mark Lesson Complete

**Endpoint**

```
POST /lessons/<lesson_id>/complete/
```

**Models**

* LearnerProgress
* Enrollment

**Logic**

* Set completed=True
* completed_at
* Recalculate:

  * course progress_percent

**Outcome**
Progress tracking works.

---

### 8. Continue Learning (Resume)

**Endpoint**

```
GET /courses/<slug>/continue/
```

**Models**

* Enrollment
* LearnerProgress
* Lesson

**Logic**

* Redirect to:

  * last incomplete required lesson
  * else → first lesson

**Outcome**
Coursera-style resume experience.

---

# PHASE 4 — ASSESSMENTS (QUIZZES)

### 9. Take Quiz

**Endpoint**

```
GET /quizzes/<quiz_id>/
```

**Models**

* Quiz
* Question
* Option
* LearnerQuizAttempt

**Rules**

* Must be enrolled
* Check max_attempts
* Randomize if enabled

---

### 10. Submit Quiz

**Endpoint**

```
POST /quizzes/<quiz_id>/submit/
```

**Models**

* LearnerQuizAttempt
* Question
* Option

**Logic**

* Auto-grade MCQ / TF
* Store raw answers in JSON
* Calculate score
* Mark graded=True

**Outcome**
Assessment feedback loop.

---

# PHASE 5 — COMPLETION & CERTIFICATION

### 11. Course Completion Check

Triggered when:

* All required lessons completed
* Required quizzes passed (policy-based)

**Models**

* Enrollment
* LearnerProgress

**Action**

* status → completed
* completed_at set

---

### 12. Certificate Generation

**Endpoint**

```
POST /courses/<slug>/certificate/
```

**Models**

* Certificate
* Enrollment

**Rules**

* Enrollment.status == completed
* One certificate per enrollment

**Outcome**
Downloadable certificate.

---

# PHASE 6 — ENGAGEMENT (SECONDARY, BUT IMPORTANT)

### 13. Discussions

**Endpoints**

```
GET /courses/<slug>/discussions/
POST /threads/create/
POST /replies/create/
```

**Models**

* DiscussionThread
* DiscussionReply

**Rules**

* Enrolled users only
* Moderation via is_deleted

---

### 14. Announcements

**Endpoint**

```
GET /courses/<slug>/announcements/
```

**Models**

* Announcement

**Rules**

* visible_from / visible_until

---

# PHASE 7 — FEEDBACK & RATINGS

### 15. Course Feedback

**Endpoint**

```
POST /courses/<slug>/feedback/
```

**Models**

* CourseFeedback

**Rules**

* Only after completion (recommended)
* One per learner per course (app-level check)

---

# PHASE 8 — OPTIONAL (Later, Not Now)

Already supported by your models, but **explicitly deferred**:

* LearningPath enrollment & progress
* Cohorts & schedules
* Assignments & peer review

We ignore these until core flow is solid.

---

# WHAT WE SHOULD BUILD NEXT (ORDER MATTERS)

**Recommended execution order:**

1. Course list & detail views
2. Enrollment logic
3. Lesson view + progress tracking
4. Continue/resume logic
5. Quiz attempt + grading
6. Course completion + certificate
7. Discussions & feedback

Each step activates the next.

---

## Final Validation

Your **models are more than sufficient** for all student-facing operations.
No schema change is required to proceed.

---

### Next question for you (important):

Do you want to proceed next with:

**A)** Student-facing FBVs (HTML + Django templates)
**B)** Student-facing APIs (DRF-first)
**C)** Hybrid (HTML now, APIs later)

Reply with **A / B / C**, and I will move directly into implementation.
