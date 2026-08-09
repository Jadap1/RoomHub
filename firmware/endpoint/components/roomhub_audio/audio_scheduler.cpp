#include "roomhub/audio_scheduler.hpp"
namespace roomhub::audio {
SubmitResult Scheduler::submit(Item item) {
    if (item.token==0) return {};
    if (has_active_ && active_.token==item.token) return {};
    for (std::size_t i=0;i<queued_;++i) if(queue_[i].token==item.token) return {};
    if (!has_active_) { active_=item; has_active_=true; return {.action=SubmitAction::start}; }
    if (item.priority>active_.priority) {
        auto interrupted=active_.token; active_=item;
        return {.action=SubmitAction::interrupt,.interrupted_token=interrupted};
    }
    if (queued_==capacity) return {};
    std::size_t position=queued_;
    while(position>0 && item.priority>queue_[position-1].priority) { queue_[position]=queue_[position-1]; --position; }
    queue_[position]=item; ++queued_; return {.action=SubmitAction::queued};
}
bool Scheduler::cancel(std::uint32_t token) {
    if(has_active_ && active_.token==token) { has_active_=false; start_next(); return true; }
    for(std::size_t i=0;i<queued_;++i) if(queue_[i].token==token) { for(std::size_t j=i+1;j<queued_;++j) queue_[j-1]=queue_[j]; --queued_; return true; }
    return false;
}
bool Scheduler::complete(std::uint32_t token) { if(!has_active_||active_.token!=token)return false; has_active_=false; start_next(); return true; }
bool Scheduler::has_active() const { return has_active_; }
Item Scheduler::active() const { return has_active_?active_:Item{}; }
std::size_t Scheduler::queued() const { return queued_; }
void Scheduler::start_next() { if(queued_==0)return; active_=queue_[0]; has_active_=true; for(std::size_t i=1;i<queued_;++i)queue_[i-1]=queue_[i]; --queued_; }
}  // namespace roomhub::audio
